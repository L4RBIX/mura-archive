"""Whisper transcription over an OpenAI-compatible HTTP API.

Two rules shape this client, and both come from what MURA records.

**Never translate.** `/audio/translations` always returns English. Only
`/audio/transcriptions` returns what was actually said, so this client calls
that endpoint and no other. A family archive that silently rendered a
grandmother's Kazakh into English would be destroying the record it exists to
keep.

**Never pin a language.** Whisper accepts an optional `language` parameter that
forces its decoder. MURA recordings routinely switch between Kazakh and Russian
inside one sentence, so forcing either mangles the other. The parameter is
deliberately never sent, and the UI language never reaches this module: what
the interface is set to says nothing about what was spoken into the microphone.

Whisper reports a single language per request. That is recorded as it was
given, and `mura.asr.language` separately reads the returned text to report
every language actually present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from mura.asr.client import ASRClientError
from mura.asr.language import read_languages
from mura.domain.models import RawSegment, TranscriptEnvelope

#: Anything below this is silence or a stray tap, not a memory.
MIN_DURATION_SECONDS = 0.05


class WhisperASRClient:
    """Transcribe audio with a hosted Whisper deployment.

    Works against any OpenAI-compatible transcription endpoint, so the same
    client serves OpenAI and the Groq/Together style hosts without a branch.
    """

    #: Whisper is reached directly over HTTPS. Unlike the tunnelled GPU worker
    #: there is no registration handshake, so the orchestrator must not defer
    #: jobs waiting for a worker row that will never appear.
    requires_registered_worker = False

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 900,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def transcribe(
        self,
        *,
        audio_path: Path,
        recording_id: str,
        content_type: str | None = None,
        worker_url: str | None = None,
    ) -> TranscriptEnvelope:
        del worker_url  # Hosted API; the orchestrator passes None.

        try:
            with audio_path.open("rb") as audio_file:
                response = self.session.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={
                        "model": self.model,
                        # Segment timestamps are required: the archive cites
                        # evidence back to a position in the audio.
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": "segment",
                        # No "language" key. See the module docstring.
                    },
                    files={
                        "file": (
                            audio_path.name,
                            audio_file,
                            content_type or "application/octet-stream",
                        )
                    },
                    timeout=(20, self.timeout_seconds),
                )
        except (OSError, requests.RequestException) as exc:
            raise ASRClientError(f"Whisper is unreachable: {exc}", retryable=True) from exc

        if response.status_code >= 400:
            raise ASRClientError(
                f"Whisper returned HTTP {response.status_code}",
                retryable=response.status_code in {408, 409, 425, 429}
                or response.status_code >= 500,
                status_code=response.status_code,
            )

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ASRClientError("Whisper returned a non-JSON body", retryable=False) from exc

        return self._envelope(payload, recording_id=recording_id)

    def _envelope(self, payload: Any, *, recording_id: str) -> TranscriptEnvelope:
        if not isinstance(payload, dict):
            raise ASRClientError("Whisper returned an unexpected body", retryable=False)

        full_text = str(payload.get("text") or "").strip()
        if not full_text:
            # An empty transcript is a failed job, never an empty success: a
            # memory that silently became nothing is worse than a visible error.
            raise ASRClientError("Whisper returned an empty transcript", retryable=False)

        segments = self._segments(payload.get("segments"), full_text=full_text)
        duration = float(payload.get("duration") or 0.0) or max(s.end for s in segments)

        reading = read_languages(full_text)
        metadata: dict[str, str | int | float | bool] = dict(reading.as_metadata)
        reported = payload.get("language")
        if isinstance(reported, str) and reported:
            # What Whisper itself claimed, kept distinct from what the text
            # shows, so a disagreement stays visible instead of being resolved
            # silently in favour of either one.
            metadata["asr_reported_language"] = reported

        return TranscriptEnvelope(
            recording_id=recording_id,
            duration_seconds=max(duration, MIN_DURATION_SECONDS),
            language_hints=list(reading.languages),
            full_text=full_text,
            segments=segments,
            asr_model=self.model,
            asr_revision=str(payload.get("model") or self.model),
            chunker_version="whisper-segments-1",
            asr_metadata=metadata,
        )

    @staticmethod
    def _segments(raw: Any, *, full_text: str) -> list[RawSegment]:
        """Whisper's segments, or one covering segment when it returns none."""

        segments: list[RawSegment] = []
        if isinstance(raw, list):
            for index, item in enumerate(raw):
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                start = float(item.get("start") or 0.0)
                end = float(item.get("end") or 0.0)
                if end <= start:
                    end = start + MIN_DURATION_SECONDS
                segments.append(
                    RawSegment(segment_id=f"seg_{index:04d}", start=start, end=end, text=text)
                )

        if not segments:
            segments.append(
                RawSegment(
                    segment_id="seg_0000", start=0.0, end=MIN_DURATION_SECONDS, text=full_text
                )
            )
        return segments
