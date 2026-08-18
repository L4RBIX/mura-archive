from __future__ import annotations

from mura.domain.models import PersonCategory, PersonMention, RelationshipRole, RelationshipType
from mura.linguistics.english import (
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


def test_english_name_match_detects_possessive_without_merging_prefixes() -> None:
    matches = find_known_name_matches("Erlan's wife is Dinara.", "Erlan")

    assert len(matches) == 1
    assert matches[0].possessive is True
    assert matches[0].rule_id == "en.name.possessive.v1"
    assert find_known_name_matches("Erlando arrived.", "Erlan") == []


def test_english_speaker_anchors_are_bounded() -> None:
    assert find_speaker_anchor_matches("My daughter is Aigul.")[0].surface == "My"
    assert find_speaker_anchor_matches("I have a son named Erlan.")[0].surface == "I have"
    assert find_speaker_anchor_matches("They have a son named Erlan.") == []


def test_english_speaker_kinship_proves_parent_direction() -> None:
    speaker = _person("mention_kulash", "Kulash")
    aigul = _person("mention_aigul", "Aigul")

    signals = find_relationship_signals(
        "My daughter is Aigul.",
        [speaker, aigul],
        speaker_name="Kulash",
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.relationship_type is RelationshipType.PARENT_CHILD
    assert signal.subject_mention_id == "mention_kulash"
    assert signal.subject_role is RelationshipRole.PARENT
    assert signal.object_mention_id == "mention_aigul"
    assert signal.object_role is RelationshipRole.CHILD


def test_english_named_possessive_proves_spouse_relation() -> None:
    erlan = _person("mention_erlan", "Erlan")
    dinara = _person("mention_dinara", "Dinara")

    signals = find_relationship_signals(
        "Erlan's wife is Dinara.",
        [erlan, dinara],
        speaker_name="Kulash",
    )

    assert len(signals) == 1
    assert signals[0].relationship_type is RelationshipType.SPOUSE
    assert {signals[0].subject_mention_id, signals[0].object_mention_id} == {
        "mention_erlan",
        "mention_dinara",
    }


def test_english_parent_direction_from_named_possessive() -> None:
    erlan = _person("mention_erlan", "Erlan")
    nurlan = _person("mention_nurlan", "Nurlan")

    signal = find_relationship_signals(
        "Nurlan is Erlan's son.",
        [erlan, nurlan],
        speaker_name="Kulash",
    )[0]

    assert signal.subject_mention_id == "mention_erlan"
    assert signal.subject_role is RelationshipRole.PARENT
    assert signal.object_mention_id == "mention_nurlan"
    assert signal.object_role is RelationshipRole.CHILD


def test_explicit_married_pair_requires_exactly_two_named_people() -> None:
    erlan = _person("mention_erlan", "Erlan")
    dinara = _person("mention_dinara", "Dinara")
    bolat = _person("mention_bolat", "Bolat")

    signals = find_relationship_signals(
        "Erlan and Dinara are married.",
        [erlan, dinara],
        speaker_name="Kulash",
    )
    assert len(signals) == 1
    assert signals[0].relationship_type is RelationshipType.SPOUSE

    assert (
        find_relationship_signals(
            "Erlan and Dinara are married, Bolat attended.",
            [erlan, dinara, bolat],
            speaker_name="Kulash",
        )
        == []
    )


def test_english_third_person_possessive_is_a_coreference_guard() -> None:
    markers = find_third_person_possessive_markers("His son Nurlan lives in Astana.")

    assert [marker.surface for marker in markers] == ["His"]
    assert markers[0].rule_id == "en.coreference.third_person_possessive_guard.v1"


def test_english_uncertainty_markers_are_non_destructive() -> None:
    markers = find_uncertainty_markers(
        "If I remember correctly, he was born approximately in 1978."
    )

    assert {marker.surface for marker in markers} == {
        "if i remember correctly",
        "approximately",
    }
