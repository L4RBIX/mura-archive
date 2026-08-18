from __future__ import annotations

from typing import Any

import pytest

from mura.coreference import augment_bounded_coreference
from mura.domain.models import (
    CoreferenceStatus,
    ExtractionResult,
    GrammaticalNumber,
    PersonMention,
    RawSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    TranscriptEnvelope,
)
from mura.extraction_sanitizer import sanitize_extraction_output


def _transcript(*texts: str) -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_coref_positive",
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


def _person(mention_id: str, name: str, segment_id: str) -> dict[str, Any]:
    return {
        "mention_id": mention_id,
        "name": name,
        "category": "family_member",
        "source_segment_ids": [segment_id],
        "confidence": 1.0,
    }


def _relationship(
    relationship_id: str,
    relationship_type: str,
    subject_id: str,
    subject_role: str,
    object_id: str,
    object_role: str,
    segment_id: str,
) -> dict[str, Any]:
    return {
        "relationship_id": relationship_id,
        "relationship_type": relationship_type,
        "subject_mention_id": subject_id,
        "subject_role": subject_role,
        "object_mention_id": object_id,
        "object_role": object_role,
        "source_segment_ids": [segment_id],
        "confidence": 1.0,
    }


def _sanitize(
    transcript: TranscriptEnvelope,
    *,
    people: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
):
    raw = {
        "recording_id": transcript.recording_id,
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["ru", "kk"],
        "people_mentions": people,
        "relationship_claims": relationships,
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


_SINGULAR_CASES = [
    (
        ("Ермек уехал.", "У него жена Сауле."),
        [
            _person("ermek", "Ермек", "seg_001"),
            _person("saule", "Сауле", "seg_002"),
        ],
        _relationship("r1", "spouse", "ermek", "spouse", "saule", "spouse", "seg_002"),
        "У него",
        "ermek",
    ),
    (
        ("Алия работает учителем.", "У неё дочь Мадина."),
        [
            _person("aliya", "Алия", "seg_001"),
            _person("madina", "Мадина", "seg_002"),
        ],
        _relationship(
            "r1",
            "parent_child",
            "aliya",
            "parent",
            "madina",
            "child",
            "seg_002",
        ),
        "У неё",
        "aliya",
    ),
    (
        ("Әкемнің аты Сапар.", "Оның інісі Нұрғали еді."),
        [
            _person("sapar", "Сапар", "seg_001"),
            _person("nurgali", "Нұрғали", "seg_002"),
        ],
        _relationship(
            "r1",
            "sibling",
            "sapar",
            "older_sibling",
            "nurgali",
            "younger_sibling",
            "seg_002",
        ),
        "Оның",
        "sapar",
    ),
    (
        ("Мой брат Ермек.", "У него жена Сауле."),
        [
            _person("speaker", "Күләш", "seg_001"),
            _person("ermek", "Ермек", "seg_001"),
            _person("saule", "Сауле", "seg_002"),
        ],
        _relationship("r1", "spouse", "ermek", "spouse", "saule", "spouse", "seg_002"),
        "У него",
        "ermek",
    ),
    (
        ("Ермек уехал. У него жена Сауле.",),
        [
            _person("ermek", "Ермек", "seg_001"),
            _person("saule", "Сауле", "seg_001"),
        ],
        _relationship("r1", "spouse", "ermek", "spouse", "saule", "spouse", "seg_001"),
        "У него",
        "ermek",
    ),
    (
        ("Ермек уехал.", "Он брат Сауле."),
        [
            _person("ermek", "Ермек", "seg_001"),
            _person("saule", "Сауле", "seg_002"),
        ],
        _relationship("r1", "sibling", "ermek", "sibling", "saule", "sibling", "seg_002"),
        "Он",
        "ermek",
    ),
]


@pytest.mark.parametrize(
    ("texts", "people", "relationship", "anaphor", "antecedent"),
    _SINGULAR_CASES,
)
def test_unique_singular_link_survives_full_sanitizer(
    texts: tuple[str, ...],
    people: list[dict[str, Any]],
    relationship: dict[str, Any],
    anaphor: str,
    antecedent: str,
) -> None:
    transcript = _transcript(*texts)
    result, issues, _ = _sanitize(
        transcript,
        people=people,
        relationships=[relationship],
    )

    assert issues == []
    assert len(result.relationship_claims) == 1
    assert len(result.coreference_links) == 1
    link = result.coreference_links[0]
    assert link.status is CoreferenceStatus.RESOLVED
    assert link.grammatical_number is GrammaticalNumber.SINGULAR
    assert link.anaphor_text == anaphor
    assert link.antecedent_mention_ids == [antecedent]
    assert result.relationship_claims[0].coreference_link_ids == [link.coreference_id]
    assert set(link.antecedent_mention_ids).issubset(
        {item.mention_id for item in result.people_mentions}
    )
    assert set(link.evidence_ids).issubset({item.evidence_id for item in result.evidence_spans})
    assert set(link.source_segment_ids).issubset({item.segment_id for item in transcript.segments})


def test_ru_explicit_plural_pair_links_all_named_children() -> None:
    transcript = _transcript(
        "Данияр и Жанар поженились.",
        "У них двое детей: Амина и Тимур.",
    )
    people = [
        _person("daniyar", "Данияр", "seg_001"),
        _person("zhanar", "Жанар", "seg_001"),
        _person("amina", "Амина", "seg_002"),
        _person("timur", "Тимур", "seg_002"),
    ]
    relationships = [
        _relationship(
            f"r_{parent}_{child}",
            "parent_child",
            parent,
            "parent",
            child,
            "child",
            "seg_002",
        )
        for parent in ("daniyar", "zhanar")
        for child in ("amina", "timur")
    ]

    result, issues, _ = _sanitize(
        transcript,
        people=people,
        relationships=relationships,
    )

    assert issues == []
    assert len(result.relationship_claims) == 4
    assert len(result.coreference_links) == 1
    link = result.coreference_links[0]
    assert link.status is CoreferenceStatus.RESOLVED
    assert link.grammatical_number is GrammaticalNumber.PLURAL
    assert link.anaphor_text == "У них"
    assert set(link.antecedent_mention_ids) == {"daniyar", "zhanar"}
    assert all(
        relationship.coreference_link_ids == [link.coreference_id]
        for relationship in result.relationship_claims
    )


def test_kk_explicit_plural_pair_materializes_link_without_claim_target() -> None:
    transcript = _transcript(
        "Данияр мен Жанар үйленді.",
        "Олардың екі баласы бар.",
    )
    result, issues, _ = _sanitize(
        transcript,
        people=[
            _person("daniyar", "Данияр", "seg_001"),
            _person("zhanar", "Жанар", "seg_001"),
        ],
        relationships=[],
    )

    assert issues == []
    assert result.relationship_claims == []
    assert len(result.coreference_links) == 1
    link = result.coreference_links[0]
    assert link.status is CoreferenceStatus.RESOLVED
    assert link.grammatical_number is GrammaticalNumber.PLURAL
    assert set(link.antecedent_mention_ids) == {"daniyar", "zhanar"}
    assert link.evidence_ids


def test_bounded_coreference_replay_is_deterministic_and_idempotent() -> None:
    transcript = _transcript("Ермек уехал.", "У него жена Сауле.")
    extraction = ExtractionResult(
        recording_id=transcript.recording_id,
        speaker_id="speaker_1",
        speaker_name="Күләш",
        people_mentions=[
            PersonMention(
                mention_id="ermek",
                name="Ермек",
                category="family_member",
                source_segment_ids=["seg_001"],
                confidence=1,
            ),
            PersonMention(
                mention_id="saule",
                name="Сауле",
                category="family_member",
                source_segment_ids=["seg_002"],
                confidence=1,
            ),
        ],
        relationship_claims=[
            RelationshipClaim(
                relationship_id="r1",
                relationship_type=RelationshipType.SPOUSE,
                subject_mention_id="ermek",
                subject_role=RelationshipRole.SPOUSE,
                object_mention_id="saule",
                object_role=RelationshipRole.SPOUSE,
                source_segment_ids=["seg_002"],
                confidence=1,
            )
        ],
    )

    first = augment_bounded_coreference(extraction, transcript)
    second = augment_bounded_coreference(first.result, transcript)

    assert first.generated_link_count == 1
    assert second.generated_link_count == 0
    assert first.result.model_dump(mode="json") == second.result.model_dump(mode="json")
