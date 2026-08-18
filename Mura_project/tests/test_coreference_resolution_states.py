from mura.domain.models import CoreferenceStatus, RawSegment, TranscriptEnvelope
from mura.extraction_sanitizer import sanitize_extraction_output


def test_plural_pronoun_with_one_candidate_is_unresolved_not_invalid_ambiguous() -> None:
    transcript = TranscriptEnvelope(
        recording_id="rec_plural_unresolved",
        duration_seconds=20,
        language_hints=["en"],
        full_text="Erlan is an engineer. Their son is Nurlan.",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text="Erlan is an engineer.",
            ),
            RawSegment(
                segment_id="seg_002",
                start=10,
                end=20,
                text="Their son is Nurlan.",
            ),
        ],
        asr_model="benchmark-fixture",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )
    raw = {
        "recording_id": transcript.recording_id,
        "speaker_id": "speaker_1",
        "speaker_name": "Kulash",
        "languages": ["en"],
        "people_mentions": [
            {
                "mention_id": "mention_erlan",
                "name": "Erlan",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_nurlan",
                "name": "Nurlan",
                "category": "family_member",
                "source_segment_ids": ["seg_002"],
                "confidence": 1.0,
            },
        ],
        "relationship_claims": [
            {
                "relationship_id": "relationship_parent",
                "relationship_type": "parent_child",
                "subject_mention_id": "mention_erlan",
                "subject_role": "parent",
                "object_mention_id": "mention_nurlan",
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

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Kulash",
    )

    assert result.relationship_claims == []
    assert len(result.coreference_links) == 1
    link = result.coreference_links[0]
    assert link.status is CoreferenceStatus.UNRESOLVED
    assert link.antecedent_mention_ids == []
    assert link.candidate_mention_ids == ["mention_erlan"]
    assert "discourse.unresolved.insufficient_candidates.v1" in link.reason
    assert any(item["object_id"] == "relationship_parent" for item in issues)
