from __future__ import annotations

import importlib

import mura.deepseek as deepseek_package
from mura.deepseek.grounding_metrics import relationship_grounding_counters
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import ExtractionResult, RawSegment, TranscriptEnvelope


def _transcript() -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_metrics",
        duration_seconds=1,
        full_text="Alex",
        segments=[RawSegment(segment_id="seg_001", start=0, end=1, text="Alex")],
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def test_relationship_telemetry_is_pure_and_counts_unique_rejections() -> None:
    issue = {
        "stage": "relationship_grounding",
        "object_type": "relationship",
        "object_id": "relationship_rejected",
        "code": "relationship_grounding_rejected",
        "severity": "error",
        "recoverable": False,
        "detail_safe": "candidate relationship was not supported by local evidence",
        "related_ids": [],
    }
    result = ExtractionResult(
        recording_id="rec_metrics",
        speaker_id="speaker_1",
        speaker_name="Narrator",
    )

    first = relationship_grounding_counters(
        result=result,
        transcript=_transcript(),
        extraction_issues=[issue, issue],
    )
    second = relationship_grounding_counters(
        result=result,
        transcript=_transcript(),
        extraction_issues=[issue, issue],
    )

    assert first == second
    assert first["ambiguous_grounding_rejected"] == 1
    assert all(isinstance(value, int) and not isinstance(value, bool) for value in first.values())
    assert "Alex" not in repr(first)


def test_repeated_package_import_does_not_replace_extract_method() -> None:
    original = DeepSeekPipelineService.__dict__["extract"]

    importlib.reload(deepseek_package)
    importlib.reload(deepseek_package)

    assert DeepSeekPipelineService.__dict__["extract"] is original
    assert not hasattr(DeepSeekPipelineService.extract, "_relationship_telemetry_installed")
