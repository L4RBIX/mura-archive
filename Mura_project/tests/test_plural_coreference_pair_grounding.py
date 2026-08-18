from __future__ import annotations

import pytest

from mura.coreference import augment_bounded_coreference
from mura.deepseek.discourse_telemetry import discourse_link_counters
from mura.domain.models import (
    CoreferenceStatus,
    ExtractionResult,
    PersonMention,
    RawSegment,
    TranscriptEnvelope,
)
from mura.explicit_pair_grounding import find_explicit_pair_matches


def _person(mention_id: str, name: str, segment_id: str) -> PersonMention:
    return PersonMention(
        mention_id=mention_id,
        name=name,
        category="family_member",
        source_segment_ids=[segment_id],
        confidence=1,
    )


def _transcript(first: str, second: str) -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_endpoint_pair",
        duration_seconds=20,
        language_hints=["ru", "kk", "en"],
        full_text=f"{first} {second}",
        segments=[
            RawSegment(segment_id="seg_001", start=0, end=10, text=first),
            RawSegment(segment_id="seg_002", start=10, end=20, text=second),
        ],
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def _augment(first: str, second: str, left: str, right: str) -> ExtractionResult:
    transcript = _transcript(first, second)
    result = ExtractionResult(
        recording_id=transcript.recording_id,
        speaker_id="speaker_1",
        speaker_name="Күләш",
        people_mentions=[
            _person("left", left, "seg_001"),
            _person("right", right, "seg_001"),
        ],
    )
    return augment_bounded_coreference(result, transcript).result


@pytest.mark.parametrize(
    ("first", "second", "left", "right"),
    [
        ("Данияр и Жанар поженились.", "У них двое детей.", "Данияр", "Жанар"),
        ("Данияр и Жанар — супруги.", "У них двое детей.", "Данияр", "Жанар"),
        (
            "Супруги Данияр и Жанар воспитывают детей.",
            "У них есть дочь Амина.",
            "Данияр",
            "Жанар",
        ),
        (
            "Сапар и Гүлмира были мужем и женой.",
            "У них родилась Күләш.",
            "Сапар",
            "Гүлмира",
        ),
        ("Алия вышла замуж за Армана.", "У них одна дочь.", "Алия", "Арман"),
        (
            "Данияр и Жанар сначала учились вместе, а потом поженились.",
            "У них двое детей.",
            "Данияр",
            "Жанар",
        ),
        ("Данияр мен Жанар үйленді.", "Олардың екі баласы бар.", "Данияр", "Жанар"),
        ("Данияр және Жанар жұбайлар.", "Олардың қызы Амина.", "Данияр", "Жанар"),
        ("Daniel and Zhanar married.", "They have two children.", "Daniel", "Zhanar"),
        (
            "Spouses Daniel and Zhanar have a daughter.",
            "Their daughter is Amina.",
            "Daniel",
            "Zhanar",
        ),
    ],
)
def test_endpoint_specific_pairs_resolve_plural_coreference(
    first: str,
    second: str,
    left: str,
    right: str,
) -> None:
    result = _augment(first, second, left, right)

    assert len(result.coreference_links) == 1
    link = result.coreference_links[0]
    assert link.status is CoreferenceStatus.RESOLVED
    assert set(link.antecedent_mention_ids) == {"left", "right"}
    assert discourse_link_counters(result)["plural_coreference_resolved"] == 1
    evidence = {item.evidence_id: item for item in result.evidence_spans}
    assert evidence[link.evidence_ids[0]].text == first
    assert evidence[link.evidence_ids[0]].start_char == 0
    assert evidence[link.evidence_ids[0]].end_char == len(first)


@pytest.mark.parametrize(
    ("first", "left", "right"),
    [
        ("Данияр и Серик работали вместе, а соседи поженились.", "Данияр", "Серик"),
        (
            "Данияр и Серик работали вместе, а Алия и Арман поженились.",
            "Данияр",
            "Серик",
        ),
        ("Соседи поженились, а Данияр и Серик продолжили работать.", "Данияр", "Серик"),
        ("Данияр и Жанар не женаты.", "Данияр", "Жанар"),
        ("Данияр и Жанар раньше были женаты, но развелись.", "Данияр", "Жанар"),
        ("Данияр и Серик друзья.", "Данияр", "Серик"),
        ("Данияр и Серик, пока соседи женились, работали вместе.", "Данияр", "Серик"),
        ("Данияр, Жанар и Серик встретились, а соседи поженились.", "Жанар", "Серик"),
        ("Серик и Серик поженились.", "Серик", "Серик"),
        ("Әсем и Нұржан встречаются.", "Әсем", "Нұржан"),
        ("Роза тәте и Татьяна почти как семья.", "Роза", "Татьяна"),
        ("Данияр и Серик работали, и соседи поженились.", "Данияр", "Серик"),
        ("Данияр и Серик работали, а потом соседи поженились.", "Данияр", "Серик"),
    ],
)
def test_unowned_pair_cues_do_not_resolve_plural_coreference(
    first: str,
    left: str,
    right: str,
) -> None:
    result = _augment(first, "У них двое детей.", left, right)

    assert result.coreference_links == []
    assert discourse_link_counters(result)["plural_coreference_resolved"] == 0


def test_pair_match_offsets_are_exact_raw_codepoint_offsets() -> None:
    text = "Күләш және Нұржан жұбайлар."
    matches = find_explicit_pair_matches(
        text,
        [
            _person("kulash", "Күләш", "seg_001"),
            _person("nurzhan", "Нұржан", "seg_001"),
        ],
    )

    assert len(matches) == 1
    match = matches[0]
    assert text[match.pair_start : match.pair_end] == "Күләш және Нұржан"
    assert text[match.cue_start : match.cue_end] == "жұбайлар"
    assert match.source_surface == "Күләш және Нұржан жұбайлар"
