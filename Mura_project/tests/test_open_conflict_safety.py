from __future__ import annotations

from typing import Any

from mura.domain.models import RawSegment, TranscriptEnvelope
from mura.extraction_sanitizer import sanitize_extraction_output


def _transcript() -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_conflict_safety",
        duration_seconds=5,
        full_text="Alex Sam",
        segments=[RawSegment(segment_id="seg_001", start=0, end=5, text="Alex Sam")],
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def _conflict(first_id: str, second_id: str) -> dict[str, Any]:
    return {
        "conflict_id": "conflict_open",
        "conflict_type": "relationship",
        "claim_refs": [
            {"object_type": "relationship", "object_id": first_id},
            {"object_type": "relationship", "object_id": second_id},
        ],
        "status": "open",
        "detected_by": "model",
        "rationale": "review required",
    }


def _base() -> dict[str, Any]:
    return {
        "recording_id": "rec_conflict_safety",
        "speaker_id": "speaker_1",
        "speaker_name": "Narrator",
        "languages": ["en"],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }


def test_open_conflict_cannot_preserve_self_relationship() -> None:
    raw = {
        **_base(),
        "people_mentions": [
            {
                "mention_id": "mention_alex",
                "name": "Alex",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            }
        ],
        "relationship_claims": [
            {
                "relationship_id": "relationship_self",
                "relationship_type": "spouse",
                "subject_mention_id": "mention_alex",
                "subject_role": "spouse",
                "object_mention_id": "mention_alex",
                "object_role": "spouse",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            }
        ],
        "conflict_sets": [_conflict("relationship_self", "relationship_placeholder")],
    }

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=_transcript(),
        speaker_id="speaker_1",
        speaker_name="Narrator",
    )

    assert result.relationship_claims == []
    assert any(
        item["object_id"] == "relationship_self" and item["stage"] == "schema" for item in issues
    )


def test_open_conflict_does_not_authorize_invalid_model_evidence() -> None:
    raw = {
        **_base(),
        "evidence_spans": [
            {
                "evidence_id": "evidence_invented",
                "segment_id": "seg_001",
                "text": "not in transcript",
                "source_layer": "raw_transcript",
                "evidence_class": "A_explicit",
                "purposes": ["claim"],
                "mention_ids": ["mention_alex", "mention_sam"],
                "confidence": 1.0,
            }
        ],
        "people_mentions": [
            {
                "mention_id": "mention_alex",
                "name": "Alex",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_sam",
                "name": "Sam",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
        ],
        "relationship_claims": [
            {
                "relationship_id": "relationship_spouse",
                "relationship_type": "spouse",
                "subject_mention_id": "mention_alex",
                "subject_role": "spouse",
                "object_mention_id": "mention_sam",
                "object_role": "spouse",
                "source_segment_ids": ["seg_001"],
                "evidence_ids": ["evidence_invented"],
                "confidence": 0.5,
            },
            {
                "relationship_id": "relationship_parent",
                "relationship_type": "parent_child",
                "subject_mention_id": "mention_alex",
                "subject_role": "parent",
                "object_mention_id": "mention_sam",
                "object_role": "child",
                "source_segment_ids": ["seg_001"],
                "evidence_ids": ["evidence_invented"],
                "confidence": 0.5,
            },
        ],
        "conflict_sets": [_conflict("relationship_spouse", "relationship_parent")],
    }

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=_transcript(),
        speaker_id="speaker_1",
        speaker_name="Narrator",
    )

    assert "evidence_invented" not in {item.evidence_id for item in result.evidence_spans}
    assert any(
        item["object_id"] == "evidence_invented" and item["code"] == "evidence_text_not_in_source"
        for item in issues
    )
    assert all(
        "evidence_invented" not in relationship.evidence_ids
        for relationship in result.relationship_claims
    )
