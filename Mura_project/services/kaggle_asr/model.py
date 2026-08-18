from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from mura.domain.models import RawSegment, TranscriptEnvelope
from services.kaggle_asr.artifacts import (
    GIGAAM_MODEL_COMMIT,
    GIGAAM_MODEL_ID,
    GIGAAM_MODEL_VARIANT,
    SnapshotArtifacts,
    download_pinned_snapshot,
    safe_model_metadata,
    verify_silero_version,
)
from services.kaggle_asr.audio import audio_duration_seconds, convert_to_wav, ffmpeg_version
from services.kaggle_asr.chunking import (
    CHUNKER_VERSION,
    ChunkRecord,
    SpeechRegion,
    TranscriptPart,
    apply_edge_padding,
    build_smart_ranges,
    merge_transcript_parts_with_diagnostics,
)


class GigaAMTranscriber:
    model_id = GIGAAM_MODEL_ID
    model_variant = GIGAAM_MODEL_VARIANT
    revision = GIGAAM_MODEL_COMMIT
    chunker_version = CHUNKER_VERSION

    def __init__(self, *, device: str = "cuda:0", hf_token: str | None = None) -> None:
        self.device = device
        self.hf_token = hf_token
        self._model: Any | None = None
        self._vad_model: Any | None = None
        self._artifacts: SnapshotArtifacts | None = None
        self._vad_version: str | None = None

    def load(self) -> None:
        import torch
        from silero_vad import load_silero_vad
        from transformers import AutoModel

        if self.loaded:
            return
        if not torch.cuda.is_available() and self.device.startswith("cuda"):
            raise RuntimeError("CUDA is not available")

        artifacts = download_pinned_snapshot(token=self.hf_token)
        vad_version = verify_silero_version()
        # The upstream architecture requires custom Transformers code. Mura never executes it from
        # a mutable branch: the complete snapshot is downloaded at an immutable commit, hashed, and
        # then loaded from the local snapshot only.
        # B615 applies to mutable Hub downloads. This call reads only the locally hashed snapshot
        # returned by download_pinned_snapshot() at GIGAAM_MODEL_COMMIT.
        model = AutoModel.from_pretrained(  # nosec B615
            str(artifacts.snapshot_path),
            trust_remote_code=True,
            local_files_only=True,
        ).to(self.device)
        model.eval()
        self._model = model
        self._vad_model = load_silero_vad()
        self._artifacts = artifacts
        self._vad_version = vad_version

    @property
    def loaded(self) -> bool:
        return self._model is not None and self._vad_model is not None

    @property
    def artifact_metadata(self) -> dict[str, str | int | float | bool]:
        if self._artifacts is None:
            return {
                "model_id": self.model_id,
                "model_variant": self.model_variant,
                "model_commit": self.revision,
                "chunker_version": self.chunker_version,
            }
        return safe_model_metadata(
            self._artifacts,
            chunker_version=self.chunker_version,
            vad_version=self._vad_version or "unknown",
        )

    def transcribe(
        self,
        *,
        input_path: Path,
        work_dir: Path,
        recording_id: str,
        max_audio_seconds: float | None = None,
    ) -> TranscriptEnvelope:
        import soundfile as sf
        import torch
        from silero_vad import get_speech_timestamps

        if not self.loaded:
            self.load()
        assert self._model is not None
        assert self._vad_model is not None
        assert self._artifacts is not None

        started = time.perf_counter()
        wav_path = work_dir / "audio_16k_mono.wav"
        chunks_dir = work_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        convert_to_wav(input_path, wav_path)
        duration = audio_duration_seconds(wav_path)
        if max_audio_seconds is not None and duration > max_audio_seconds:
            raise RuntimeError(
                f"audio exceeds maximum duration: {duration:.1f}s > {max_audio_seconds:.1f}s"
            )

        waveform, sample_rate = sf.read(str(wav_path), dtype="float32")
        if waveform.ndim > 1:
            waveform = waveform.mean(axis=1)
        if sample_rate != 16_000:
            raise RuntimeError(f"unexpected sample rate: {sample_rate}")
        if len(waveform) == 0:
            raise RuntimeError("decoded audio is empty")

        regions_raw = get_speech_timestamps(
            torch.from_numpy(waveform.copy()),
            self._vad_model,
            sampling_rate=sample_rate,
            threshold=0.50,
            min_speech_duration_ms=200,
            min_silence_duration_ms=250,
            max_speech_duration_s=20.0,
            speech_pad_ms=150,
            return_seconds=False,
        )
        if not regions_raw:
            raise RuntimeError("Silero VAD detected no speech")

        regions = [SpeechRegion(int(item["start"]), int(item["end"])) for item in regions_raw]
        smart_ranges = build_smart_ranges(regions, sample_rate=sample_rate)
        padded_ranges = apply_edge_padding(
            smart_ranges,
            sample_rate=sample_rate,
            total_samples=len(waveform),
        )

        records: list[ChunkRecord] = []
        for index, region in enumerate(padded_ranges, start=1):
            chunk_path = chunks_dir / f"chunk_{index:03d}.wav"
            sf.write(
                str(chunk_path),
                waveform[region.start_sample : region.end_sample],
                sample_rate,
                subtype="PCM_16",
            )
            records.append(
                ChunkRecord(
                    index=index,
                    path=chunk_path,
                    start=region.start_sample / sample_rate,
                    end=region.end_sample / sample_rate,
                )
            )

        parts: list[TranscriptPart] = []
        segments: list[RawSegment] = []
        empty_chunk_count = 0
        for record in records:
            with torch.inference_mode():
                output = self._model.transcribe(str(record.path), word_timestamps=False)
            text = self._extract_text(output)
            parts.append(TranscriptPart(chunk=record, text=text))
            if not text:
                empty_chunk_count += 1
                continue
            segments.append(
                RawSegment(
                    segment_id=f"seg_{record.index:03d}",
                    chunk_id=f"chunk_{record.index:03d}",
                    start=round(record.start, 3),
                    end=round(record.end, 3),
                    text=text,
                )
            )

        full_text, merge_diagnostics = merge_transcript_parts_with_diagnostics(parts)
        if not segments or not full_text:
            raise RuntimeError("ASR produced no text for detected speech")

        metadata = safe_model_metadata(
            self._artifacts,
            model_variant=self.model_variant,
            vad_version=self._vad_version or "unknown",
            chunk_count=len(records),
            empty_chunk_count=empty_chunk_count,
            overlap_boundaries=merge_diagnostics.overlap_boundaries,
            duplicate_words_removed=merge_diagnostics.duplicate_words_removed,
            ffmpeg_version=ffmpeg_version(),
        )
        return TranscriptEnvelope(
            recording_id=recording_id,
            duration_seconds=round(duration, 3),
            full_text=full_text,
            segments=segments,
            asr_model=self.model_id,
            asr_revision=self.revision,
            chunker_version=self.chunker_version,
            processing_seconds=round(time.perf_counter() - started, 3),
            asr_metadata=metadata,
        )

    @staticmethod
    def _extract_text(output: object) -> str:
        if hasattr(output, "text"):
            return str(output.text).strip()
        if isinstance(output, dict):
            return str(output.get("text", "")).strip()
        return str(output).strip()
