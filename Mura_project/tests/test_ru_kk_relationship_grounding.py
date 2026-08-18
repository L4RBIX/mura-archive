from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from mura.domain.models import RawSegment, TranscriptEnvelope
from mura.extraction_sanitizer import sanitize_extraction_output

PersonSpec = tuple[str, str, str | None]
RelationSpec = tuple[str, str, str, str, str, str]


@dataclass(frozen=True)
class GroundingCase:
    text: str
    people: tuple[PersonSpec, ...]
    relationships: tuple[RelationSpec, ...]


def _person(spec: PersonSpec) -> dict[str, Any]:
    mention_id, name, relation_to_speaker = spec
    return {
        "mention_id": mention_id,
        "name": name,
        "category": "family_member",
        "relation_to_speaker": relation_to_speaker,
        "source_segment_ids": ["seg_001"],
        "evidence_ids": ["evidence_1"],
        "confidence": 1.0,
    }


def _relationship(spec: RelationSpec) -> dict[str, Any]:
    (
        relationship_id,
        relationship_type,
        subject_id,
        subject_role,
        object_id,
        object_role,
    ) = spec
    return {
        "relationship_id": relationship_id,
        "relationship_type": relationship_type,
        "subject_mention_id": subject_id,
        "subject_role": subject_role,
        "object_mention_id": object_id,
        "object_role": object_role,
        "source_segment_ids": ["seg_001"],
        "evidence_ids": ["evidence_1"],
        "confidence": 1.0,
    }


def _sanitize(
    case: GroundingCase,
    *,
    speaker_name: str = "Күләш",
    evidence: bool = True,
    relationship_overrides: dict[str, Any] | None = None,
) -> tuple[Any, list[dict[str, Any]]]:
    transcript = TranscriptEnvelope(
        recording_id="rec_grounding",
        duration_seconds=10,
        language_hints=["ru", "kk"],
        full_text=case.text,
        segments=[RawSegment(segment_id="seg_001", start=0, end=10, text=case.text)],
        asr_model="relationship-grounding-fixture",
        asr_revision="v1",
        chunker_version="v1",
    )
    people = [_person(item) for item in case.people]
    relationships = [_relationship(item) for item in case.relationships]
    if relationship_overrides:
        relationships[0].update(relationship_overrides)
    evidence_spans: list[dict[str, Any]] = []
    if evidence:
        evidence_spans.append(
            {
                "evidence_id": "evidence_1",
                "segment_id": "seg_001",
                "text": case.text,
                "source_layer": "raw_transcript",
                "start_char": 0,
                "end_char": len(case.text),
                "evidence_class": "A_explicit",
                "purposes": ["claim"],
                "mention_ids": [item[0] for item in case.people],
                "confidence": 1.0,
            }
        )
    raw = {
        "recording_id": transcript.recording_id,
        "speaker_id": "speaker_1",
        "speaker_name": speaker_name,
        "languages": ["ru", "kk"],
        "provenance_activities": [],
        "evidence_spans": evidence_spans,
        "coreference_links": [],
        "conflict_sets": [],
        "people_mentions": people,
        "relationship_claims": relationships,
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }
    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name=speaker_name,
    )
    return result, issues


_ACCEPTED_CASES = [
    GroundingCase(
        "Мой сын Данияр.",
        (("speaker", "Күләш", "self"), ("child", "Данияр", "son")),
        (("r1", "parent_child", "speaker", "parent", "child", "child"),),
    ),
    GroundingCase(
        "Моя дочь Алия.",
        (("speaker", "Күләш", "self"), ("child", "Алия", "daughter")),
        (("r1", "parent_child", "speaker", "parent", "child", "child"),),
    ),
    GroundingCase(
        "Наш младший сын Нұржан.",
        (("speaker", "Күләш", "self"), ("child", "Нұржан", "son")),
        (("r1", "parent_child", "speaker", "parent", "child", "child"),),
    ),
    GroundingCase(
        "Менің ұлым Данияр.",
        (("speaker", "Күләш", "self"), ("child", "Данияр", "son")),
        (("r1", "parent_child", "speaker", "parent", "child", "child"),),
    ),
    GroundingCase(
        "Менің қызым Алия.",
        (("speaker", "Күләш", "self"), ("child", "Алия", "daughter")),
        (("r1", "parent_child", "speaker", "parent", "child", "child"),),
    ),
    GroundingCase(
        "У нас трое детей: Данияр, Алия и Нұржан.",
        (
            ("speaker", "Күләш", "self"),
            ("daniyar", "Данияр", "son"),
            ("aliya", "Алия", "daughter"),
            ("nurzhan", "Нұржан", "son"),
        ),
        tuple(
            (f"r_{child}", "parent_child", "speaker", "parent", child, "child")
            for child in ("daniyar", "aliya", "nurzhan")
        ),
    ),
    GroundingCase(
        "Мой муж Марат.",
        (("speaker", "Күләш", "self"), ("marat", "Марат", "husband")),
        (("r1", "spouse", "speaker", "spouse", "marat", "spouse"),),
    ),
    GroundingCase(
        "Менің күйеуім Марат.",
        (("speaker", "Күләш", "self"), ("marat", "Марат", "husband")),
        (("r1", "spouse", "speaker", "spouse", "marat", "spouse"),),
    ),
    GroundingCase(
        "Мой брат Ермек.",
        (("speaker", "Күләш", "self"), ("ermek", "Ермек", "brother")),
        (("r1", "sibling", "speaker", "sibling", "ermek", "sibling"),),
    ),
    GroundingCase(
        "Моя младшая сестра Айгүл.",
        (("speaker", "Күләш", "self"), ("aigul", "Айгүл", "sister")),
        (("r1", "sibling", "speaker", "older_sibling", "aigul", "younger_sibling"),),
    ),
    GroundingCase(
        "Менің ағам Ермек.",
        (("speaker", "Күләш", "self"), ("ermek", "Ермек", "brother")),
        (("r1", "sibling", "ermek", "older_sibling", "speaker", "younger_sibling"),),
    ),
    GroundingCase(
        "Менің сіңлім Айгүл.",
        (("speaker", "Күләш", "self"), ("aigul", "Айгүл", "sister")),
        (("r1", "sibling", "speaker", "older_sibling", "aigul", "younger_sibling"),),
    ),
    GroundingCase(
        "Жена Данияра — Жанар.",
        (("daniyar", "Данияр", None), ("zhanar", "Жанар", None)),
        (("r1", "spouse", "daniyar", "spouse", "zhanar", "spouse"),),
    ),
    GroundingCase(
        "Муж Алии — Арман.",
        (("aliya", "Алия", None), ("arman", "Арман", None)),
        (("r1", "spouse", "aliya", "spouse", "arman", "spouse"),),
    ),
    GroundingCase(
        "Сын Айгүл — Руслан.",
        (("aigul", "Айгүл", None), ("ruslan", "Руслан", None)),
        (("r1", "parent_child", "aigul", "parent", "ruslan", "child"),),
    ),
    GroundingCase(
        "Дочь Алии и Армана — Мадина.",
        (("aliya", "Алия", None), ("arman", "Арман", None), ("madina", "Мадина", None)),
        (
            ("r_aliya", "parent_child", "aliya", "parent", "madina", "child"),
            ("r_arman", "parent_child", "arman", "parent", "madina", "child"),
        ),
    ),
    GroundingCase(
        "У Данияра и Жанар двое детей: Амина и Тимур.",
        (
            ("daniyar", "Данияр", None),
            ("zhanar", "Жанар", None),
            ("amina", "Амина", None),
            ("timur", "Тимур", None),
        ),
        tuple(
            (f"r_{parent}_{child}", "parent_child", parent, "parent", child, "child")
            for parent in ("daniyar", "zhanar")
            for child in ("amina", "timur")
        ),
    ),
    GroundingCase(
        "Сапар и Гүлмира поженились.",
        (("sapar", "Сапар", None), ("gulmira", "Гүлмира", None)),
        (("r1", "spouse", "sapar", "spouse", "gulmira", "spouse"),),
    ),
    GroundingCase(
        "Данияр и Жанар поженились.",
        (("daniyar", "Данияр", None), ("zhanar", "Жанар", None)),
        (("r1", "spouse", "daniyar", "spouse", "zhanar", "spouse"),),
    ),
    GroundingCase(
        "Ермек и Айгүл — брат и сестра.",
        (("ermek", "Ермек", None), ("aigul", "Айгүл", None)),
        (("r1", "sibling", "ermek", "sibling", "aigul", "sibling"),),
    ),
]


@pytest.mark.parametrize("case", _ACCEPTED_CASES, ids=lambda item: item.text)
def test_explicit_ru_kk_relationship_is_accepted(case: GroundingCase) -> None:
    result, issues = _sanitize(case)

    assert issues == []
    assert {item.relationship_id for item in result.relationship_claims} == {
        item[0] for item in case.relationships
    }


_REJECTED_CASES = [
    GroundingCase(
        "Әсем — девушка Нұржана, но не жена.",
        (("nurzhan", "Нұржан", None), ("asem", "Әсем", None)),
        (("r1", "spouse", "nurzhan", "spouse", "asem", "spouse"),),
    ),
    GroundingCase(
        "У моего сына Нұржана есть девушка Әсем.",
        (("nurzhan", "Нұржан", "son"), ("asem", "Әсем", None)),
        (("r1", "spouse", "nurzhan", "spouse", "asem", "spouse"),),
    ),
    GroundingCase(
        "Роза тәте не родственница.",
        (("speaker", "Күләш", "self"), ("roza", "Роза", None)),
        (("r1", "sibling", "speaker", "sibling", "roza", "sibling"),),
    ),
    GroundingCase(
        "Татьяна почти как член семьи.",
        (("speaker", "Күләш", "self"), ("tatiana", "Татьяна", None)),
        (("r1", "sibling", "speaker", "sibling", "tatiana", "sibling"),),
    ),
    GroundingCase(
        "Серик помогал Марату с ремонтом.",
        (("serik", "Серик", None), ("marat", "Марат", None)),
        (("r1", "sibling", "serik", "sibling", "marat", "sibling"),),
    ),
    GroundingCase(
        "Серик — двоюродный брат Марата.",
        (("serik", "Серик", None), ("marat", "Марат", None)),
        (("r1", "sibling", "serik", "sibling", "marat", "sibling"),),
    ),
    GroundingCase(
        "Нұржан и Әсем встречаются.",
        (("nurzhan", "Нұржан", None), ("asem", "Әсем", None)),
        (("r1", "spouse", "nurzhan", "spouse", "asem", "spouse"),),
    ),
    GroundingCase(
        "Серик Оразбаев приехал. Серик Ахметов помогал с ремонтом.",
        (("serik_1", "Серик Оразбаев", None), ("serik_2", "Серик Ахметов", None)),
        (("r1", "sibling", "serik_1", "sibling", "serik_2", "sibling"),),
    ),
    GroundingCase(
        "Ерлан встретил Болата. Его сын Нурлан живёт в Астане.",
        (
            ("erlan", "Ерлан", None),
            ("bolat", "Болат", None),
            ("nurlan", "Нурлан", None),
        ),
        (("r1", "parent_child", "erlan", "parent", "nurlan", "child"),),
    ),
    GroundingCase(
        "Ерлан жил в Караганде. Потом семья переехала. Прошло много лет. Его дочь Амина учится.",
        (("erlan", "Ерлан", None), ("amina", "Амина", None)),
        (("r1", "parent_child", "erlan", "parent", "amina", "child"),),
    ),
]


@pytest.mark.parametrize("case", _REJECTED_CASES, ids=lambda item: item.text)
def test_adversarial_language_does_not_create_family_edge(case: GroundingCase) -> None:
    result, issues = _sanitize(case)

    assert result.relationship_claims == []
    assert any(item.get("object_type") == "relationship" for item in issues)


def test_wrong_parent_child_direction_is_quarantined() -> None:
    case = GroundingCase(
        "Амина — дочь Данияра.",
        (("daniyar", "Данияр", None), ("amina", "Амина", None)),
        (("r1", "parent_child", "amina", "parent", "daniyar", "child"),),
    )

    result, issues = _sanitize(case)

    assert result.relationship_claims == []
    assert any(item["code"] == "relationship_grounding_rejected" for item in issues)


def test_self_relationship_is_rejected_by_schema() -> None:
    case = GroundingCase(
        "Күләш өзі туралы айтты.",
        (("kulash", "Күләш", "self"),),
        (("r1", "spouse", "kulash", "spouse", "kulash", "spouse"),),
    )

    result, issues = _sanitize(case)

    assert result.relationship_claims == []
    assert any(item["stage"] == "schema" for item in issues)


def test_invalid_source_segment_cannot_create_relationship() -> None:
    case = GroundingCase(
        "У Данияра есть дочь Амина.",
        (("daniyar", "Данияр", None), ("amina", "Амина", None)),
        (("r1", "parent_child", "daniyar", "parent", "amina", "child"),),
    )

    result, issues = _sanitize(
        case,
        evidence=False,
        relationship_overrides={
            "source_segment_ids": ["seg_missing"],
            "evidence_ids": ["missing_evidence"],
        },
    )

    assert result.relationship_claims == []
    assert any(item["code"] == "object_reference_invalid" for item in issues)


def test_valid_evidence_and_references_are_preserved() -> None:
    case = GroundingCase(
        "Жена Данияра — Жанар.",
        (("daniyar", "Данияр", None), ("zhanar", "Жанар", None)),
        (("r1", "spouse", "daniyar", "spouse", "zhanar", "spouse"),),
    )

    result, issues = _sanitize(case)

    assert issues == []
    relationship = result.relationship_claims[0]
    assert relationship.evidence_ids == ["evidence_1"]
    assert relationship.provenance is not None
    assert relationship.provenance.evidence_ids == ["evidence_1"]
    assert {relationship.subject_mention_id, relationship.object_mention_id}.issubset(
        {item.mention_id for item in result.people_mentions}
    )
    assert set(relationship.evidence_ids).issubset(
        {item.evidence_id for item in result.evidence_spans}
    )
