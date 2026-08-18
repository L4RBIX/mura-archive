from __future__ import annotations

from mura.domain.models import (
    PersonMention,
    RawSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    TranscriptEnvelope,
)
from mura.relationship_evidence import analyze_relationship_evidence
from mura.relationship_grounding import GroundingContext, find_bounded_relationship_signals


def _person(
    mention_id: str,
    name: str,
    relation_to_speaker: str | None = None,
) -> PersonMention:
    return PersonMention(
        mention_id=mention_id,
        name=name,
        category="family_member",
        relation_to_speaker=relation_to_speaker,
        source_segment_ids=["seg_001"],
        confidence=1,
    )


def _signals(text: str, people: list[PersonMention]):
    return find_bounded_relationship_signals(
        contexts=[GroundingContext(text=text, sentence_count=1)],
        people=people,
        speaker_name="Күләш",
    )


def _spouse_signals(text: str, people: list[PersonMention]):
    return [
        signal
        for signal in _signals(text, people)
        if signal.relationship_type is RelationshipType.SPOUSE
    ]


def test_unrelated_marriage_predicate_does_not_ground_endpoint_spouses() -> None:
    text = "Данияр и Серик работали вместе, а соседи поженились."
    people = [_person("daniyar", "Данияр"), _person("serik", "Серик")]

    assert _spouse_signals(text, people) == []

    transcript = TranscriptEnvelope(
        recording_id="rec_relationship_pair",
        duration_seconds=10,
        full_text=text,
        segments=[RawSegment(segment_id="seg_001", start=0, end=10, text=text)],
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )
    claim = RelationshipClaim(
        relationship_id="r1",
        relationship_type=RelationshipType.SPOUSE,
        subject_mention_id="daniyar",
        subject_role=RelationshipRole.SPOUSE,
        object_mention_id="serik",
        object_role=RelationshipRole.SPOUSE,
        source_segment_ids=["seg_001"],
        confidence=1,
    )
    analysis = analyze_relationship_evidence(
        relationship=claim,
        transcript=transcript,
        people=people,
        speaker_name="Күләш",
    )
    assert analysis.matching_signal_rule_ids == []
    assert analysis.auto_accept_eligible is False


def test_positive_pair_has_one_canonical_signal_in_both_endpoint_orders() -> None:
    text = "Данияр и Жанар поженились."
    forward = [_person("daniyar", "Данияр"), _person("zhanar", "Жанар")]
    reverse = list(reversed(forward))

    first = _spouse_signals(text, forward)
    second = _spouse_signals(text, reverse)

    assert len(first) == 1
    assert len(second) == 1
    assert {
        first[0].subject_mention_id,
        first[0].object_mention_id,
    } == {"daniyar", "zhanar"}
    assert first[0].to_dict() == second[0].to_dict()
    assert first[0].source_surface == "Данияр и Жанар поженились"


def test_direct_spouse_predicate_is_bound_to_exact_endpoints() -> None:
    text = "Алия вышла замуж за Армана."
    people = [_person("aliya", "Алия"), _person("arman", "Арман")]

    signals = _spouse_signals(text, people)

    assert len(signals) == 1
    assert {signals[0].subject_mention_id, signals[0].object_mention_id} == {
        "aliya",
        "arman",
    }
    assert signals[0].source_surface == "Алия вышла замуж за Армана"
    assert signals[0].rule_id == "ru.relationship.explicit_spouse_direct.v1"


def test_parent_labels_still_ground_endpoint_specific_spouse_pair() -> None:
    people = [
        _person("sapar", "Сапар", "father"),
        _person("gulmira", "Гүлмира", "mother"),
    ]

    signals = _spouse_signals("Отец и мама были мужем и женой.", people)

    assert len(signals) == 1
    assert {signals[0].subject_mention_id, signals[0].object_mention_id} == {
        "sapar",
        "gulmira",
    }


def test_named_parent_child_and_sibling_paths_are_unchanged() -> None:
    parent_child = _signals(
        "Дочь Алии — Мадина.",
        [_person("aliya", "Алия"), _person("madina", "Мадина")],
    )
    sibling = _signals(
        "Ермек и Айгүл — брат и сестра.",
        [_person("ermek", "Ермек"), _person("aigul", "Айгүл")],
    )

    assert any(signal.relationship_type is RelationshipType.PARENT_CHILD for signal in parent_child)
    assert any(signal.relationship_type is RelationshipType.SIBLING for signal in sibling)


def test_other_named_pair_cue_is_not_transferred_to_candidate_endpoints() -> None:
    text = "Данияр и Серик работали вместе, а Алия и Арман поженились."
    people = [_person("daniyar", "Данияр"), _person("serik", "Серик")]

    assert _spouse_signals(text, people) == []
