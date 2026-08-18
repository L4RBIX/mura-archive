from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from mura.domain.models import StrictModel
from mura.evaluation.asr import AsrEvaluationCase, AsrEvaluationDataset
from services.kaggle_asr.model import GigaAMTranscriber


class LiveAudioCase(StrictModel):
    case_id: str = Field(min_length=1)
    language: Literal["ru", "kk", "mixed"]
    audio_path: Path
    reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_local_relative_path(self) -> LiveAudioCase:
        if self.audio_path.is_absolute() or ".." in self.audio_path.parts:
            raise ValueError("audio_path must stay inside the manifest directory")
        return self


class LiveAudioManifest(StrictModel):
    schema_version: str = "asr-live-manifest-v1"
    dataset_id: str
    source_type: Literal["public_licensed", "approved_private"]
    license_or_consent: str
    cases: list[LiveAudioCase] = Field(min_length=1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run pinned GigaAM on approved local audio.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dataset", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--max-audio-seconds", type=float, default=1800.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest_path = Path(args.manifest).resolve()
    manifest = LiveAudioManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if args.max_audio_seconds <= 0:
        raise ValueError("max-audio-seconds must be positive")
    transcriber = GigaAMTranscriber(device=args.device, hf_token=os.getenv("HF_TOKEN"))
    output_cases: list[AsrEvaluationCase] = []
    with tempfile.TemporaryDirectory(prefix="mura-live-asr-") as directory:
        root = Path(directory)
        for index, case in enumerate(manifest.cases, start=1):
            audio_path = (manifest_path.parent / case.audio_path).resolve()
            if manifest_path.parent not in audio_path.parents or not audio_path.is_file():
                raise FileNotFoundError(case.audio_path)
            work_dir = root / f"case-{index:03d}"
            work_dir.mkdir()
            transcript = transcriber.transcribe(
                input_path=audio_path,
                work_dir=work_dir,
                recording_id=case.case_id,
                max_audio_seconds=args.max_audio_seconds,
            )
            output_cases.append(
                AsrEvaluationCase(
                    case_id=case.case_id,
                    language=case.language,
                    reference=case.reference,
                    hypothesis=transcript.full_text,
                )
            )
    dataset = AsrEvaluationDataset(
        dataset_id=manifest.dataset_id,
        source_type=manifest.source_type,
        license_or_consent=manifest.license_or_consent,
        description="Live pinned GigaAM hypotheses generated from approved audio fixtures.",
        runtime_metadata=transcriber.artifact_metadata,
        cases=output_cases,
    )
    Path(args.output_dataset).write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
