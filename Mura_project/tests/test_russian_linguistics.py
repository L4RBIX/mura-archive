from __future__ import annotations

import pytest

from mura.domain.models import PersonCategory, PersonMention, RelationshipRole, RelationshipType
from mura.linguistics.russian import (
    find_known_name_matches,
    find_relationship_signals,
    find_speaker_anchor_matches,
    find_third_person_possessive_markers,
    find_uncertainty_markers,
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
    ("text", "expected_case"),
    [
        ("Ерлан пришёл", "nominative"),
        ("жена Ерлана", "genitive"),
        ("позвонили Ерлану", "dative"),
        ("говорили с Ерланом", "instrumental"),
        ("думали о Ерлане", "prepositional"),
        ("жена Динары", "genitive"),
        ("позвонили Динаре", "dative_or_prepositional"),
    ],
)
def test_known_russian_name_matches_only_audited_forms(
    text: str,
    expected_case: str,
) -> None:
    surface = "Динара" if "Динар" in text else "Ерлан"
    matches = find_known_name_matches(text, surface)

    assert len(matches) == 1
    assert matches[0].grammatical_case == expected_case


def test_russian_name_matching_rejects_unrelated_prefixes() -> None:
    assert find_known_name_matches("Ерланов выступил", "Ерлан") == []
    assert find_known_name_matches("Ерланбек пришёл", "Ерлан") == []


def test_russian_speaker_anchors_include_inflected_possessives() -> None:
    anchors = find_speaker_anchor_matches("Мою младшую дочь зовут Айгуль.")

    assert [anchor.surface for anchor in anchors] == ["Мою"]
    assert anchors[0].rule_id == "ru.speaker.possessive_pronoun.v1"
    assert find_speaker_anchor_matches("У меня сын Ерлан.")[0].surface == "У меня"


def test_russian_speaker_kinship_proves_parent_direction() -> None:
    speaker = _person("mention_kulash", "Күләш")
    aigul = _person("mention_aigul", "Айгуль")

    signals = find_relationship_signals(
        "Мою младшую дочь зовут Айгуль.",
        [speaker, aigul],
        speaker_name="Күләш",
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.relationship_type is RelationshipType.PARENT_CHILD
    assert signal.subject_mention_id == "mention_kulash"
    assert signal.subject_role is RelationshipRole.PARENT
    assert signal.object_mention_id == "mention_aigul"
    assert signal.object_role is RelationshipRole.CHILD


def test_russian_named_genitive_proves_spouse_relation() -> None:
    erlan = _person("mention_erlan", "Ерлан")
    dinara = _person("mention_dinara", "Динара")

    signals = find_relationship_signals(
        "Жена Ерлана — Динара.",
        [erlan, dinara],
        speaker_name="Күләш",
    )

    assert len(signals) == 1
    assert signals[0].relationship_type is RelationshipType.SPOUSE
    assert {signals[0].subject_mention_id, signals[0].object_mention_id} == {
        "mention_erlan",
        "mention_dinara",
    }


def test_russian_sibling_age_order_is_canonical() -> None:
    erlan = _person("mention_erlan", "Ерлан")
    bolat = _person("mention_bolat", "Болат")

    signal = find_relationship_signals(
        "Старший брат Ерлана — Болат.",
        [erlan, bolat],
        speaker_name="Күләш",
    )[0]

    assert signal.subject_mention_id == "mention_bolat"
    assert signal.subject_role is RelationshipRole.OLDER_SIBLING
    assert signal.object_mention_id == "mention_erlan"
    assert signal.object_role is RelationshipRole.YOUNGER_SIBLING


def test_russian_relationship_signal_requires_one_named_target() -> None:
    speaker = _person("mention_kulash", "Күләш")
    erlan = _person("mention_erlan", "Ерлан")
    bolat = _person("mention_bolat", "Болат")

    assert (
        find_relationship_signals(
            "Мой сын Ерлан или Болат.",
            [speaker, erlan, bolat],
            speaker_name="Күләш",
        )
        == []
    )


def test_russian_third_person_possessive_is_a_coreference_guard() -> None:
    markers = find_third_person_possessive_markers("Его сын Нурлан живёт в Астане.")

    assert [marker.surface for marker in markers] == ["Его"]
    assert markers[0].rule_id == "ru.coreference.third_person_possessive_guard.v1"


def test_russian_uncertainty_markers_are_non_destructive() -> None:
    markers = find_uncertainty_markers("Если не ошибаюсь, он родился примерно в 1978 году.")

    assert {marker.surface for marker in markers} == {"если не ошибаюсь", "примерно"}
