from __future__ import annotations

from typing import Any

from mura.domain.models import CoreferenceStatus, RawSegment, TranscriptEnvelope
from mura.extraction_sanitizer import sanitize_extraction_output


def _transcript(*texts: str) -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_coref_guards",
        duration_seconds=float(len(texts) * 10),
        language_hints=["ru", "kk"],
        full_text=" ".join(texts),
        segments=[
            RawSegment(
                segment_id=f"seg_{index:03d}",
                start=float((index - 1) * 10),
                end=float(index * 10),
                text=text,
            )
            for index, text in enumerate(texts, start=1)
        ],
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def _person(mention_id: str, name: str, *segment_ids: str) -> dict[str, Any]:
    return {
        "mention_id": mention_id,
        "name": name,
        "category": "family_member",
        "source_segment_ids": list(segment_ids),
        "confidence": 1.0,
    }


def _relationship(
    relationship_id: str,
    relationship_type: str,
    subject_id: str,
    subject_role: str,
    object_id: str,
    object_role: str,
    *segment_ids: str,
) -> dict[str, Any]:
    return {
        "relationship_id": relationship_id,
        "relationship_type": relationship_type,
        "subject_mention_id": subject_id,
        "subject_role": subject_role,
        "object_mention_id": object_id,
        "object_role": object_role,
        "source_segment_ids": list(segment_ids),
        "confidence": 1.0,
    }


def _sanitize(
    transcript: TranscriptEnvelope,
    *,
    people: list[dict[str, Any]],
    relationships: list[dict[str, Any]] | None = None,
):
    raw = {
        "recording_id": transcript.recording_id,
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["ru", "kk"],
        "people_mentions": people,
        "relationship_claims": relationships or [],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
        "coreference_links": [],
        "conflict_sets": [],
        "evidence_spans": [],
        "provenance_activities": [],
    }
    return sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )


def _resolved_links(result) -> list:
    return [link for link in result.coreference_links if link.status is CoreferenceStatus.RESOLVED]


def test_two_singular_candidates_are_not_guessed() -> None:
    transcript = _transcript(
        "Серик говорил с Ермеком.",
        "У него жена Сауле.",
    )
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("serik", "Серик", "seg_001"),
            _person("ermek", "Ермек", "seg_001"),
            _person("saule", "Сауле", "seg_002"),
        ],
        relationships=[
            _relationship(
                "r1",
                "spouse",
                "serik",
                "spouse",
                "saule",
                "spouse",
                "seg_002",
            )
        ],
    )

    assert _resolved_links(result) == []
    assert result.relationship_claims == []
    assert any(item["object_id"] == "r1" for item in issues)
    assert all(link.antecedent_mention_ids == [] for link in result.coreference_links)


def test_two_names_without_explicit_plural_group_do_not_resolve() -> None:
    transcript = _transcript(
        "Данияр видел Жанар.",
        "У них двое детей.",
    )
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("daniyar", "Данияр", "seg_001"),
            _person("zhanar", "Жанар", "seg_001"),
        ],
    )

    assert issues == []
    assert result.coreference_links == []


def test_pronoun_in_third_sentence_is_outside_window() -> None:
    transcript = _transcript("Ермек уехал. Погода испортилась. У него жена Сауле.")
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("ermek", "Ермек", "seg_001"),
            _person("saule", "Сауле", "seg_001"),
        ],
        relationships=[
            _relationship(
                "r1",
                "spouse",
                "ermek",
                "spouse",
                "saule",
                "spouse",
                "seg_001",
            )
        ],
    )

    assert _resolved_links(result) == []
    assert result.relationship_claims == []
    assert any(item["object_id"] == "r1" for item in issues)


def test_antecedent_outside_420_characters_is_not_used() -> None:
    transcript = _transcript(
        "Ермек " + ("очень далеко " * 40),
        "У него жена Сауле.",
    )
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("ermek", "Ермек", "seg_001"),
            _person("saule", "Сауле", "seg_002"),
        ],
        relationships=[
            _relationship(
                "r1",
                "spouse",
                "ermek",
                "spouse",
                "saule",
                "spouse",
                "seg_002",
            )
        ],
    )

    assert _resolved_links(result) == []
    assert result.relationship_claims == []
    assert any(item["object_id"] == "r1" for item in issues)


def test_quarantined_or_unknown_antecedent_cannot_resolve() -> None:
    transcript = _transcript("У него жена Сауле.")
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("ermek", "Ермек", "seg_missing"),
            _person("saule", "Сауле", "seg_001"),
        ],
        relationships=[
            _relationship(
                "r1",
                "spouse",
                "ermek",
                "spouse",
                "saule",
                "spouse",
                "seg_001",
            )
        ],
    )

    assert _resolved_links(result) == []
    assert result.relationship_claims == []
    assert {item["object_type"] for item in issues}.issuperset({"person", "relationship"})


def test_non_person_reference_does_not_create_link() -> None:
    transcript = _transcript(
        "Дом стоит у реки.",
        "У него большая крыша.",
    )
    result, issues, _ = _sanitize(transcript, people=[])

    assert issues == []
    assert result.coreference_links == []


def test_feminine_pronoun_does_not_choose_by_name_gender() -> None:
    transcript = _transcript(
        "Алия встретила Данияра.",
        "У неё дочь Мадина.",
    )
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("aliya", "Алия", "seg_001"),
            _person("daniyar", "Данияр", "seg_001"),
            _person("madina", "Мадина", "seg_002"),
        ],
        relationships=[
            _relationship(
                "r1",
                "parent_child",
                "aliya",
                "parent",
                "madina",
                "child",
                "seg_002",
            )
        ],
    )

    assert _resolved_links(result) == []
    assert result.relationship_claims == []
    assert any(item["object_id"] == "r1" for item in issues)


def test_cross_recording_or_unknown_segment_antecedent_is_rejected() -> None:
    transcript = _transcript("У него жена Сауле.")
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("external", "Ермек", "other_recording_segment"),
            _person("saule", "Сауле", "seg_001"),
        ],
    )

    assert _resolved_links(result) == []
    assert any(
        item["object_type"] == "person" and item["object_id"] == "external" for item in issues
    )


def test_respectful_address_and_almost_family_do_not_create_kinship() -> None:
    transcript = _transcript(
        "Роза тәте пришла.",
        "Она почти как родственница.",
    )
    result, issues, _ = _sanitize(
        transcript,
        people=[_person("roza", "Роза", "seg_001")],
    )

    assert any(issue["code"] == "person_category_downgraded" for issue in issues)
    assert result.relationship_claims == []
    assert result.coreference_links == []


def test_dating_pair_and_plural_pronoun_do_not_create_spouse() -> None:
    transcript = _transcript(
        "Әсем встречается с Нұржаном.",
        "Они живут рядом.",
    )
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("asem", "Әсем", "seg_001"),
            _person("nurzhan", "Нұржан", "seg_001"),
        ],
        relationships=[
            _relationship(
                "r1",
                "spouse",
                "asem",
                "spouse",
                "nurzhan",
                "spouse",
                "seg_002",
            )
        ],
    )

    assert result.relationship_claims == []
    assert result.coreference_links == []
    assert any(item["object_id"] == "r1" for item in issues)


def test_self_relationship_stays_schema_invalid() -> None:
    transcript = _transcript("Ермек. Он брат Ермека.")
    result, issues, _ = _sanitize(
        transcript,
        people=[_person("ermek", "Ермек", "seg_001")],
        relationships=[
            _relationship(
                "r1",
                "sibling",
                "ermek",
                "sibling",
                "ermek",
                "sibling",
                "seg_001",
            )
        ],
    )

    assert result.relationship_claims == []
    assert any(item["stage"] == "schema" and item["object_id"] == "r1" for item in issues)


def test_plural_pronoun_with_three_people_is_ambiguous() -> None:
    transcript = _transcript(
        "Данияр, Жанар и Ермек встретились.",
        "У них дети.",
    )
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("daniyar", "Данияр", "seg_001"),
            _person("zhanar", "Жанар", "seg_001"),
            _person("ermek", "Ермек", "seg_001"),
        ],
    )

    assert issues == []
    assert _resolved_links(result) == []
    assert result.coreference_links == []
