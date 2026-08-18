from __future__ import annotations

from mura.domain.models import RawSegment, TranscriptEnvelope
from mura.extraction_sanitizer import sanitize_extraction_output


def test_specific_russian_sibling_phrase_overrides_nested_generic_term() -> None:
    transcript = TranscriptEnvelope(
        recording_id="rec_ru_specific_sibling",
        duration_seconds=10,
        language_hints=["ru"],
        full_text="Старший брат Ерлана — Болат.",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text="Старший брат Ерлана — Болат.",
            )
        ],
        asr_model="benchmark-fixture",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )
    raw: dict[str, object] = {
        "recording_id": transcript.recording_id,
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["ru"],
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
        ],
        "relationship_claims": [
            {
                "relationship_id": "relationship_older_sibling",
                "relationship_type": "sibling",
                "subject_mention_id": "mention_bolat",
                "subject_role": "older_sibling",
                "object_mention_id": "mention_erlan",
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

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert issues == []
    assert [item.relationship_id for item in result.relationship_claims] == [
        "relationship_older_sibling"
    ]
