from __future__ import annotations

import pytest

from mura.domain.models import (
    PersonCategory,
    PersonMention,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
)
from mura.linguistics.kazakh import (
    find_known_name_matches,
    find_relationship_signals,
    find_speaker_anchor_matches,
    find_uncertainty_markers,
    has_speaker_anchor,
    signal_matches_relationship,
)


def _person(mention_id: str, name: str) -> PersonMention:
    return PersonMention(
        mention_id=mention_id,
        name=name,
        category=PersonCategory.FAMILY_MEMBER,
        source_segment_ids=["seg_001"],
        confidence=1.0,
    )


@pytest.mark.parametrize(
    ("text", "expected_suffix"),
    [
        ("Ерлан", None),
        ("Ерланның әйелі", "ның"),
        ("Ерланға бардық", "ға"),
        ("Ерланмен сөйлестік", "мен"),
        ("Ерланды көрдік", "ды"),
        ("Ерланнан естідім", "нан"),
    ],
)
def test_known_kazakh_name_matches_only_audited_case_suffixes(
    text: str,
    expected_suffix: str | None,
) -> None:
    matches = find_known_name_matches(text, "Ерлан")

    assert len(matches) == 1
    assert matches[0].suffix == expected_suffix
    assert matches[0].rule_id in {"kk.name.exact.v1", "kk.name.known_case_suffix.v1"}


def test_known_name_matching_does_not_use_unrestricted_prefixes() -> None:
    assert find_known_name_matches("Ерланбек келді", "Ерлан") == []
    assert find_known_name_matches("Ермек келді", "Ер") == []


def test_speaker_anchors_distinguish_pronoun_from_coordination() -> None:
    assert has_speaker_anchor("Менің інім Болат.")
    assert has_speaker_anchor("Әкемнің аты Сапар.")
    assert has_speaker_anchor("Ал мен Болаттың ағасымын.")

    assert not has_speaker_anchor("Ерлан мен Динара үйленді.")
    assert not has_speaker_anchor("Оның ұлы Нұрлан.")


def test_speaker_anchor_returns_inspectable_rules() -> None:
    matches = find_speaker_anchor_matches("Біздің ұлымыз Ерлан.")

    assert {match.rule_id for match in matches} == {
        "kk.speaker.explicit_pronoun.v1",
        "kk.speaker.possessive_kinship.v1",
    }


def test_speaker_possessive_kinship_proves_parent_direction() -> None:
    speaker = _person("mention_kulash", "Күләш")
    sapar = _person("mention_sapar", "Сапар")

    signals = find_relationship_signals(
        "Әкемнің аты Сапар.",
        [speaker, sapar],
        speaker_name="Күләш",
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.relationship_type is RelationshipType.PARENT_CHILD
    assert signal.subject_mention_id == "mention_sapar"
    assert signal.subject_role is RelationshipRole.PARENT
    assert signal.object_mention_id == "mention_kulash"
    assert signal.object_role is RelationshipRole.CHILD


def test_speaker_sibling_term_preserves_age_order() -> None:
    speaker = _person("mention_kulash", "Күләш")
    bolat = _person("mention_bolat", "Болат")

    signals = find_relationship_signals(
        "Менің інім Болат.",
        [speaker, bolat],
        speaker_name="Күләш",
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.relationship_type is RelationshipType.SIBLING
    assert signal.subject_mention_id == "mention_kulash"
    assert signal.subject_role is RelationshipRole.OLDER_SIBLING
    assert signal.object_mention_id == "mention_bolat"
    assert signal.object_role is RelationshipRole.YOUNGER_SIBLING


def test_speaker_kinship_requires_exactly_one_named_target() -> None:
    speaker = _person("mention_kulash", "Күләш")
    bolat = _person("mention_bolat", "Болат")
    erlan = _person("mention_erlan", "Ерлан")

    signals = find_relationship_signals(
        "Менің інім Болат немесе Ерлан.",
        [speaker, bolat, erlan],
        speaker_name="Күләш",
    )

    assert signals == []


def test_named_genitive_kinship_proves_spouse_relation() -> None:
    erlan = _person("mention_erlan", "Ерлан")
    dinara = _person("mention_dinara", "Динара")

    signals = find_relationship_signals(
        "Ерланның әйелі Динара.",
        [erlan, dinara],
        speaker_name="Күләш",
    )

    assert len(signals) == 1
    assert signals[0].relationship_type is RelationshipType.SPOUSE
    assert {
        signals[0].subject_mention_id,
        signals[0].object_mention_id,
    } == {"mention_erlan", "mention_dinara"}


def test_named_sibling_term_rejects_reversed_roles() -> None:
    sapar = _person("mention_sapar", "Сапар")
    nurgali = _person("mention_nurgali", "Нұрғали")
    signal = find_relationship_signals(
        "Сапардың інісі Нұрғали.",
        [sapar, nurgali],
        speaker_name="Күләш",
    )[0]
    reversed_relationship = RelationshipClaim(
        relationship_id="relationship_reversed",
        relationship_type=RelationshipType.SIBLING,
        subject_mention_id="mention_nurgali",
        subject_role=RelationshipRole.OLDER_SIBLING,
        object_mention_id="mention_sapar",
        object_role=RelationshipRole.YOUNGER_SIBLING,
        source_segment_ids=["seg_001"],
        confidence=1.0,
    )

    assert not signal_matches_relationship(signal, reversed_relationship)


def test_uncertainty_markers_are_preserved_as_annotations() -> None:
    markers = find_uncertainty_markers("Ол шамамен 1942 жылы туған сияқты.")

    assert {marker.surface for marker in markers} == {"шамамен", "сияқты"}
    assert {marker.rule_id for marker in markers} == {"kk.uncertainty.lexical_marker.v1"}
