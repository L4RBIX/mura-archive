from __future__ import annotations

from mura.domain.models import EvidenceClass, RawSegment, TranscriptEnvelope
from mura.extraction_sanitizer import sanitize_extraction_output


def _transcript(recording_id: str, text: str, languages: list[str]) -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id=recording_id,
        duration_seconds=10,
        language_hints=languages,
        full_text=text,
        segments=[RawSegment(segment_id="seg_001", start=0, end=10, text=text)],
        asr_model="benchmark-fixture",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )


def _raw(
    *,
    recording_id: str,
    speaker_name: str,
    languages: list[str],
    people: list[dict[str, object]],
    relationship: dict[str, object],
) -> dict[str, object]:
    return {
        "recording_id": recording_id,
        "speaker_id": "speaker_1",
        "speaker_name": speaker_name,
        "languages": languages,
        "people_mentions": people,
        "relationship_claims": [relationship],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }


def test_russian_inflected_speaker_relationship_is_accepted() -> None:
    transcript = _transcript(
        "rec_ru_speaker",
        "Мою младшую дочь зовут Айгуль.",
        ["ru"],
    )
    raw = _raw(
        recording_id=transcript.recording_id,
        speaker_name="Күләш",
        languages=["ru"],
        people=[
            {
                "mention_id": "mention_kulash",
                "name": "Күләш",
                "category": "family_member",
                "relation_to_speaker": "self",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_aigul",
                "name": "Айгуль",
                "category": "family_member",
                "relation_to_speaker": "daughter",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
        ],
        relationship={
            "relationship_id": "relationship_parent",
            "relationship_type": "parent_child",
            "subject_mention_id": "mention_kulash",
            "subject_role": "parent",
            "object_mention_id": "mention_aigul",
            "object_role": "child",
            "source_segment_ids": ["seg_001"],
            "confidence": 1.0,
        },
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert issues == []
    assert [item.relationship_id for item in result.relationship_claims] == ["relationship_parent"]
    relationship = result.relationship_claims[0]
    assert relationship.evidence_class is EvidenceClass.C_SPEAKER_ANCHORED
    assert relationship.provenance is not None
    assert relationship.provenance.pipeline_versions["pipeline"] == "mura-core-v0.15.0"


def test_russian_third_person_possessive_is_quarantined() -> None:
    transcript = _transcript(
        "rec_ru_ambiguous",
        "Ерлан встретил Болата. Его сын Нурлан живёт в Астане.",
        ["ru"],
    )
    raw = _raw(
        recording_id=transcript.recording_id,
        speaker_name="Күләш",
        languages=["ru"],
        people=[
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
        relationship={
            "relationship_id": "relationship_ambiguous",
            "relationship_type": "parent_child",
            "subject_mention_id": "mention_erlan",
            "subject_role": "parent",
            "object_mention_id": "mention_nurlan",
            "object_role": "child",
            "source_segment_ids": ["seg_001"],
            "confidence": 1.0,
        },
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.relationship_claims == []
    issue = next(item for item in issues if item["object_id"] == "relationship_ambiguous")
    assert issue["code"] == "relationship_grounding_rejected"
    assert "context" not in issue


def test_english_named_possessive_relationship_is_accepted() -> None:
    transcript = _transcript("rec_en_spouse", "Erlan's wife is Dinara.", ["en"])
    raw = _raw(
        recording_id=transcript.recording_id,
        speaker_name="Kulash",
        languages=["en"],
        people=[
            {
                "mention_id": "mention_erlan",
                "name": "Erlan",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_dinara",
                "name": "Dinara",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
        ],
        relationship={
            "relationship_id": "relationship_spouse",
            "relationship_type": "spouse",
            "subject_mention_id": "mention_erlan",
            "subject_role": "spouse",
            "object_mention_id": "mention_dinara",
            "object_role": "spouse",
            "source_segment_ids": ["seg_001"],
            "confidence": 1.0,
        },
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Kulash",
    )

    assert issues == []
    assert [item.relationship_id for item in result.relationship_claims] == ["relationship_spouse"]
    assert result.relationship_claims[0].evidence_class is EvidenceClass.A_EXPLICIT


def test_code_switching_uses_foreign_anchor_with_local_kinship() -> None:
    transcript = _transcript("rec_mixed_son", "Мой son Erlan.", ["ru", "en"])
    raw = _raw(
        recording_id=transcript.recording_id,
        speaker_name="Kulash",
        languages=["ru", "en"],
        people=[
            {
                "mention_id": "mention_kulash",
                "name": "Kulash",
                "category": "family_member",
                "relation_to_speaker": "self",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_erlan",
                "name": "Erlan",
                "category": "family_member",
                "relation_to_speaker": "son",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
        ],
        relationship={
            "relationship_id": "relationship_mixed_parent",
            "relationship_type": "parent_child",
            "subject_mention_id": "mention_kulash",
            "subject_role": "parent",
            "object_mention_id": "mention_erlan",
            "object_role": "child",
            "source_segment_ids": ["seg_001"],
            "confidence": 1.0,
        },
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Kulash",
    )

    assert issues == []
    assert [item.relationship_id for item in result.relationship_claims] == [
        "relationship_mixed_parent"
    ]
    assert result.relationship_claims[0].evidence_class is EvidenceClass.C_SPEAKER_ANCHORED


def test_generic_first_person_sentence_does_not_prove_relationship() -> None:
    transcript = _transcript("rec_ru_generic", "Я встретила Ерлана.", ["ru"])
    raw = _raw(
        recording_id=transcript.recording_id,
        speaker_name="Күләш",
        languages=["ru"],
        people=[
            {
                "mention_id": "mention_kulash",
                "name": "Күләш",
                "category": "family_member",
                "relation_to_speaker": "self",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_erlan",
                "name": "Ерлан",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
        ],
        relationship={
            "relationship_id": "relationship_false_spouse",
            "relationship_type": "spouse",
            "subject_mention_id": "mention_kulash",
            "subject_role": "spouse",
            "object_mention_id": "mention_erlan",
            "object_role": "spouse",
            "source_segment_ids": ["seg_001"],
            "confidence": 1.0,
        },
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.relationship_claims == []
    issue = next(item for item in issues if item["object_id"] == "relationship_false_spouse")
    assert issue["code"] == "object_reference_invalid"
