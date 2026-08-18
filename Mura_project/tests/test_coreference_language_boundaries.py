from __future__ import annotations

import pytest

from mura.coreference_language import AnaphorOccurrence, find_anaphors, nearest_kinship
from mura.coreference_units import NameOccurrence, target_ids
from mura.domain.models import GrammaticalNumber


@pytest.mark.parametrize(
    ("surface", "language", "number"),
    [
        ("его", "ru", GrammaticalNumber.SINGULAR),
        ("ее", "ru", GrammaticalNumber.SINGULAR),
        ("её", "ru", GrammaticalNumber.SINGULAR),
        ("он", "ru", GrammaticalNumber.SINGULAR),
        ("она", "ru", GrammaticalNumber.SINGULAR),
        ("у него", "ru", GrammaticalNumber.SINGULAR),
        ("у нее", "ru", GrammaticalNumber.SINGULAR),
        ("у неё", "ru", GrammaticalNumber.SINGULAR),
        ("их", "ru", GrammaticalNumber.PLURAL),
        ("они", "ru", GrammaticalNumber.PLURAL),
        ("у них", "ru", GrammaticalNumber.PLURAL),
        ("оның", "kk", GrammaticalNumber.SINGULAR),
        ("ол", "kk", GrammaticalNumber.SINGULAR),
        ("олардың", "kk", GrammaticalNumber.PLURAL),
        ("олар", "kk", GrammaticalNumber.PLURAL),
        ("his", "en", GrammaticalNumber.SINGULAR),
        ("her", "en", GrammaticalNumber.SINGULAR),
        ("their", "en", GrammaticalNumber.PLURAL),
    ],
)
def test_declared_anaphor_forms_are_token_aware(
    surface: str,
    language: str,
    number: GrammaticalNumber,
) -> None:
    matches = find_anaphors(f"({surface}),")

    assert len(matches) == 1
    assert matches[0].surface == surface
    assert matches[0].language == language
    assert matches[0].grammatical_number is number


def test_multi_token_ru_form_has_priority_and_preserves_case() -> None:
    matches = find_anaphors("У НЕЁ, дочь.")

    assert [(item.surface, item.grammatical_number) for item in matches] == [
        ("У НЕЁ", GrammaticalNumber.SINGULAR)
    ]


@pytest.mark.parametrize("text", ["егоист", "оникс", "оларға", "theirself"])
def test_anaphors_do_not_match_inside_other_tokens(text: str) -> None:
    assert find_anaphors(text) == []


def _anaphor() -> AnaphorOccurrence:
    return AnaphorOccurrence(
        surface="his",
        start=0,
        end=3,
        language="en",
        grammatical_number=GrammaticalNumber.SINGULAR,
    )


def test_kinship_window_accepts_32_codepoints_and_rejects_33() -> None:
    at_limit = "his" + (" " * 32) + "wife"
    beyond_limit = "his" + (" " * 33) + "wife"

    assert nearest_kinship(at_limit, _anaphor()) is not None
    assert nearest_kinship(beyond_limit, _anaphor()) is None


def test_target_window_accepts_110_codepoints_and_rejects_111() -> None:
    at_limit = NameOccurrence(mention_id="at_limit", start=110, end=111)
    beyond_limit = NameOccurrence(mention_id="beyond_limit", start=111, end=112)

    assert target_ids([at_limit, beyond_limit], kinship_end=0, unit_end=200) == ["at_limit"]
