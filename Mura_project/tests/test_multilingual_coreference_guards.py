from __future__ import annotations

from mura.domain.models import RawSegment, TranscriptEnvelope
from mura.extraction_sanitizer import sanitize_extraction_output


def test_ambiguous_coreference_id_does_not_bypass_possessive_guard() -> None:
    transcript = TranscriptEnvelope(
        recording_id="rec_ambiguous_link",
        duration_seconds=10,
        language_hints=["ru"],
        full_text="Ерлан встретил Болата. Его сын Нурлан.",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text="Ерлан встретил Болата. Его сын Нурлан.",
            )
        ],
        asr_model="benchmark-fixture",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )
    raw: dict[str, object] = {
        "schema_version": "extraction-v2",
        "recording_id": transcript.recording_id,
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["ru"],
        "evidence_spans": [
            {
                "evidence_id": "evidence_pronoun",
                "segment_id": "seg_001",
                "text": "Его",
                "source_layer": "raw_transcript",
                "evidence_class": "U_uncertain",
                "purposes": ["coreference"],
                "mention_ids": [],
                "confidence": 0.5,
            }
        ],
        "coreference_links": [
            {
                "coreference_id": "coreference_ambiguous",
                "anaphor_text": "Его",
                "source_segment_ids": ["seg_001"],
                "evidence_ids": ["evidence_pronoun"],
                "status": "ambiguous",
                "method": "model_proposal",
                "grammatical_number": "singular",
                "antecedent_mention_ids": [],
                "candidate_mention_ids": ["mention_erlan", "mention_bolat"],
                "evidence_class": "U_uncertain",
                "confidence": 0.5,
                "reason": "Two named antecedents remain possible.",
            }
        ],
        "people_mentions": [
            {
                "mention_id": "mention_erlan",
                "name": "Ерлан",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_bolat",
                "name": "Болат",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_nurlan",
                "name": "Нурлан",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
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
                "source_segment_ids": ["seg_001"],
                "coreference_link_ids": ["coreference_ambiguous"],
                "confidence": 0.5,
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
        speaker_name="Күләш",
    )

    assert result.relationship_claims == []
    issue = next(item for item in issues if item["object_id"] == "relationship_parent")
    assert issue["code"] == "relationship_grounding_rejected"
    assert "context" not in issue
