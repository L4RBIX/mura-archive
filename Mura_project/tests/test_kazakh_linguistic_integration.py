from __future__ import annotations

from mura.domain.models import EvidenceClass, RawSegment, TranscriptEnvelope
from mura.extraction_sanitizer import sanitize_extraction_output


def test_possessed_kinship_resolves_implicit_speaker_endpoint() -> None:
    transcript = TranscriptEnvelope(
        recording_id="rec_kazakh_father",
        duration_seconds=20,
        full_text="Менің атым Күләш. Әкемнің аты Сапар.",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text="менің атым күләш",
            ),
            RawSegment(
                segment_id="seg_002",
                start=10,
                end=20,
                text="әкемнің аты сапар",
            ),
        ],
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )
    raw: dict[str, object] = {
        "recording_id": "rec_kazakh_father",
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["kk"],
        "people_mentions": [
            {
                "mention_id": "mention_kulash",
                "name": "Күләш",
                "category": "family_member",
                "relation_to_speaker": "self",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_sapar",
                "name": "Сапар",
                "category": "family_member",
                "relation_to_speaker": "father",
                "source_segment_ids": ["seg_002"],
                "confidence": 1.0,
            },
        ],
        "relationship_claims": [
            {
                "relationship_id": "relationship_sapar_parent_kulash",
                "relationship_type": "parent_child",
                "subject_mention_id": "mention_sapar",
                "subject_role": "parent",
                "object_mention_id": "mention_kulash",
                "object_role": "child",
                "source_segment_ids": ["seg_002"],
                "confidence": 1.0,
            }
        ],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }

    result, issues, closure_count = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert issues == []
    assert closure_count == 1
    assert [item.relationship_id for item in result.relationship_claims] == [
        "relationship_sapar_parent_kulash"
    ]
    relationship = result.relationship_claims[0]
    assert relationship.source_segment_ids == ["seg_001", "seg_002"]
    assert relationship.evidence_class is EvidenceClass.C_SPEAKER_ANCHORED


def test_reversed_kazakh_sibling_direction_is_quarantined() -> None:
    transcript = TranscriptEnvelope(
        recording_id="rec_kazakh_sibling",
        duration_seconds=10,
        full_text="Сапардың інісі Нұрғали.",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text="сапардың інісі нұрғали",
            )
        ],
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )
    raw: dict[str, object] = {
        "recording_id": "rec_kazakh_sibling",
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["kk"],
        "people_mentions": [
            {
                "mention_id": "mention_sapar",
                "name": "Сапар",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_nurgali",
                "name": "Нұрғали",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
        ],
        "relationship_claims": [
            {
                "relationship_id": "relationship_reversed",
                "relationship_type": "sibling",
                "subject_mention_id": "mention_nurgali",
                "subject_role": "older_sibling",
                "object_mention_id": "mention_sapar",
                "object_role": "younger_sibling",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            }
        ],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }

    result, issues, closure_count = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.relationship_claims == []
    assert closure_count == 0
    relationship_issue = next(
        issue for issue in issues if issue["object_id"] == "relationship_reversed"
    )
    assert relationship_issue["code"] == "relationship_grounding_rejected"
    assert "context" not in relationship_issue
