from __future__ import annotations

from time import perf_counter
from typing import Any

import pytest

from mura.coreference import augment_bounded_coreference
from mura.domain.models import (
    ExtractionResult,
    PersonMention,
    RawSegment,
    TranscriptEnvelope,
)

_CASE_SIZE = 200
_RUNTIME_BUDGET_SECONDS = 5.0


def test_large_transcript_uses_segment_local_name_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mura import coreference_units

    original = coreference_units.find_known_name_matches
    calls = 0

    def counted(text: str, surface: str) -> list[Any]:
        nonlocal calls
        calls += 1
        return original(text, surface)

    monkeypatch.setattr(coreference_units, "find_known_name_matches", counted)
    segments = [
        RawSegment(
            segment_id=f"seg_{index:03d}",
            start=float(index),
            end=float(index + 1),
            text=f"P{index:03d} arrived. His son lives nearby.",
        )
        for index in range(_CASE_SIZE)
    ]
    transcript = TranscriptEnvelope(
        recording_id="rec_coreference_runtime",
        duration_seconds=float(_CASE_SIZE),
        language_hints=["en"],
        full_text=" ".join(segment.text for segment in segments),
        segments=segments,
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )
    extraction = ExtractionResult(
        recording_id=transcript.recording_id,
        speaker_id="speaker_1",
        speaker_name="Narrator",
        people_mentions=[
            PersonMention(
                mention_id=f"person_{index:03d}",
                name=f"P{index:03d}",
                category="family_member",
                source_segment_ids=[f"seg_{index:03d}"],
                confidence=1.0,
            )
            for index in range(_CASE_SIZE)
        ],
    )

    started = perf_counter()
    augmented = augment_bounded_coreference(extraction, transcript)
    elapsed = perf_counter() - started

    assert augmented.generated_link_count == _CASE_SIZE
    assert calls == _CASE_SIZE
    assert elapsed < _RUNTIME_BUDGET_SECONDS
