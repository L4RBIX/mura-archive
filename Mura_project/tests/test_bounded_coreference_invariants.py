from __future__ import annotations

import pytest

from mura.coreference_context import BoundedCoreferenceContext
from mura.coreference_language import AnaphorOccurrence, KinshipOccurrence
from mura.coreference_materialization import link_id_for
from mura.coreference_units import (
    MAX_CONTEXT_CHARS,
    TextUnit,
    context_units,
    segment_units,
)
from mura.domain.models import GrammaticalNumber, RelationshipRole, RelationshipType
from mura.linguistics.russian import KinshipFrame


@pytest.mark.parametrize(
    ("length", "expected_lengths"),
    [
        (MAX_CONTEXT_CHARS - 1, [MAX_CONTEXT_CHARS - 1]),
        (MAX_CONTEXT_CHARS, [MAX_CONTEXT_CHARS]),
        (MAX_CONTEXT_CHARS + 1, [MAX_CONTEXT_CHARS, 1]),
    ],
)
def test_segment_units_have_a_strict_maximum_length(
    length: int,
    expected_lengths: list[int],
) -> None:
    text = "x" * length
    units = segment_units("segment", text)

    assert [len(unit.text) for unit in units] == expected_lengths
    assert all(len(unit.text) <= MAX_CONTEXT_CHARS for unit in units)
    assert "".join(unit.text for unit in units) == text


@pytest.mark.parametrize(
    ("total_span", "expected_count"),
    [(MAX_CONTEXT_CHARS, 2), (MAX_CONTEXT_CHARS + 1, 1)],
)
def test_same_segment_context_limit_counts_trimmed_gaps(
    total_span: int,
    expected_count: int,
) -> None:
    prefix = "A."
    suffix = "His son."
    gap = " " * (total_span - len(prefix) - len(suffix))
    units = segment_units("segment", prefix + gap + suffix)

    selected = context_units(units, current_index=1)

    assert len(selected) == expected_count
    assert selected[-1].text == suffix


def _context(segment_id: str) -> BoundedCoreferenceContext:
    return BoundedCoreferenceContext(
        segment_id=segment_id,
        anaphor=AnaphorOccurrence(
            surface="his",
            start=10,
            end=13,
            language="en",
            grammatical_number=GrammaticalNumber.SINGULAR,
        ),
        kinship=KinshipOccurrence(
            surface="wife",
            start=14,
            end=18,
            language="en",
            frame=KinshipFrame(
                RelationshipType.SPOUSE,
                RelationshipRole.SPOUSE,
                RelationshipRole.SPOUSE,
            ),
        ),
        candidate_ids=["person_1"],
        target_ids=["person_2"],
        candidate_context=TextUnit(
            segment_id=segment_id,
            start=0,
            end=9,
            text="Person A.",
        ),
        resolved=True,
    )


def test_link_ids_are_stable_and_distinguish_raw_segment_ids() -> None:
    first = _context("segment-a")
    second = _context("segment_a")

    assert link_id_for(first) == link_id_for(first)
    assert link_id_for(first) != link_id_for(second)
