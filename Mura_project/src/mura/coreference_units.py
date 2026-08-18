from __future__ import annotations

import re
from dataclasses import dataclass

from mura.coreference_boundaries import quote_scope_for_span
from mura.coreference_language import AnaphorOccurrence
from mura.domain.models import PersonMention, TranscriptEnvelope
from mura.linguistics.multilingual import find_known_name_matches
from mura.relationship_evidence import person_name_surfaces


@dataclass(frozen=True)
class NameOccurrence:
    mention_id: str
    start: int
    end: int
    quote_scope: str = "outside"


@dataclass(frozen=True)
class TextUnit:
    segment_id: str
    start: int
    end: int
    text: str


_MAX_CONTEXT_UNITS = 2
MAX_CONTEXT_CHARS = 420
_TARGET_WINDOW_CHARS = 110
_UNIT_RE = re.compile(r"[^.!?…;\n]+(?:[.!?…;\n]+|$)", flags=re.UNICODE)
_STRONG_SWITCH_RE = re.compile(
    r"(?:,\s*|\s+)(?:(?:но|однако|зато|бірақ|алайда|дегенмен|however|but)\s+|"
    r"(?:а|ал)\s+(?=(?:он|она|они|ол|олар)\b))",
    flags=re.IGNORECASE | re.UNICODE,
)


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def _chunk_span(text: str, start: int, end: int) -> list[tuple[int, int]]:
    if end - start <= MAX_CONTEXT_CHARS:
        return [(start, end)]
    words = list(re.finditer(r"\S+", text[start:end], flags=re.UNICODE))
    chunks: list[tuple[int, int]] = []
    chunk_start: int | None = None
    chunk_end: int | None = None

    def flush_chunk() -> None:
        nonlocal chunk_start, chunk_end
        if chunk_start is not None and chunk_end is not None:
            chunks.append((chunk_start, chunk_end))
        chunk_start = None
        chunk_end = None

    for word in words:
        word_start = start + word.start()
        word_end = start + word.end()
        if word_end - word_start > MAX_CONTEXT_CHARS:
            flush_chunk()
            chunks.extend(
                (offset, min(offset + MAX_CONTEXT_CHARS, word_end))
                for offset in range(word_start, word_end, MAX_CONTEXT_CHARS)
            )
            continue
        if chunk_start is None:
            chunk_start = word_start
            chunk_end = word_end
            continue
        if word_end - chunk_start > MAX_CONTEXT_CHARS:
            flush_chunk()
            chunk_start = word_start
        chunk_end = word_end
    flush_chunk()
    return chunks


def _split_strong_switches(text: str, start: int, end: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    for match in _STRONG_SWITCH_RE.finditer(text, start, end):
        boundary = match.start()
        trimmed = _trimmed_span(text, cursor, boundary)
        if trimmed is not None:
            spans.append(trimmed)
        cursor = boundary
    trimmed = _trimmed_span(text, cursor, end)
    if trimmed is not None:
        spans.append(trimmed)
    return spans


def segment_units(segment_id: str, text: str) -> list[TextUnit]:
    spans: list[tuple[int, int]] = []
    for match in _UNIT_RE.finditer(text):
        trimmed = _trimmed_span(text, match.start(), match.end())
        if trimmed is not None:
            for clause_span in _split_strong_switches(text, *trimmed):
                spans.extend(_chunk_span(text, *clause_span))
    if not spans:
        trimmed = _trimmed_span(text, 0, len(text))
        if trimmed is not None:
            spans.extend(_chunk_span(text, *trimmed))
    return [
        TextUnit(segment_id=segment_id, start=start, end=end, text=text[start:end])
        for start, end in spans
    ]


def ordered_units(transcript: TranscriptEnvelope) -> list[TextUnit]:
    return [
        unit
        for segment in transcript.segments
        for unit in segment_units(segment.segment_id, segment.text)
    ]


def person_occurrences(
    text: str,
    people: list[PersonMention],
    *,
    segment_id: str,
) -> list[NameOccurrence]:
    occurrences: dict[tuple[str, int, int], NameOccurrence] = {}
    for person in people:
        if segment_id not in person.source_segment_ids:
            continue
        for surface in person_name_surfaces(person):
            for match in find_known_name_matches(text, surface):
                if match.start < 0:
                    continue
                key = (person.mention_id, match.start, match.end)
                occurrences.setdefault(
                    key,
                    NameOccurrence(
                        mention_id=person.mention_id,
                        start=match.start,
                        end=match.end,
                        quote_scope=quote_scope_for_span(text, match.start, match.end).scope_id,
                    ),
                )
    return sorted(
        occurrences.values(),
        key=lambda item: (item.start, item.end, item.mention_id),
    )


def target_ids(
    occurrences: list[NameOccurrence],
    *,
    kinship_end: int,
    unit_end: int,
    quote_scope: str = "outside",
) -> list[str]:
    return sorted(
        {
            item.mention_id
            for item in occurrences
            if item.quote_scope == quote_scope
            and kinship_end <= item.start < unit_end
            and item.start - kinship_end <= _TARGET_WINDOW_CHARS
        }
    )


def unit_index_for_anaphor(
    units: list[TextUnit],
    *,
    segment_id: str,
    anaphor: AnaphorOccurrence,
) -> int | None:
    return next(
        (
            index
            for index, unit in enumerate(units)
            if unit.segment_id == segment_id
            and unit.start <= anaphor.start
            and anaphor.end <= unit.end
        ),
        None,
    )


def _context_char_count(previous: TextUnit, current: TextUnit) -> int:
    if previous.segment_id == current.segment_id:
        return current.end - previous.start
    return len(previous.text) + 1 + len(current.text)


def context_units(units: list[TextUnit], *, current_index: int) -> list[TextUnit]:
    current = units[current_index]
    selected = [current]
    if current_index == 0:
        return selected
    previous = units[current_index - 1]
    if _context_char_count(previous, current) <= MAX_CONTEXT_CHARS:
        selected.insert(0, previous)
    return selected[-_MAX_CONTEXT_UNITS:]


def candidate_ids(
    *,
    selected_units: list[TextUnit],
    current_unit: TextUnit,
    anaphor: AnaphorOccurrence,
    excluded_ids: set[str],
    occurrences_by_segment: dict[str, list[NameOccurrence]],
    segment_text_by_id: dict[str, str],
) -> list[str]:
    anaphor_scope = quote_scope_for_span(
        segment_text_by_id[current_unit.segment_id], anaphor.start, anaphor.end
    )
    if anaphor_scope.scope_id != "outside" or anaphor_scope.malformed:
        return []
    local = {
        occurrence.mention_id
        for occurrence in occurrences_by_segment[current_unit.segment_id]
        if occurrence.mention_id not in excluded_ids
        and occurrence.quote_scope == anaphor_scope.scope_id
        and current_unit.start <= occurrence.start
        and occurrence.end <= anaphor.start
    }
    if local:
        return sorted(local)
    if len(selected_units) < 2:
        return []
    previous = selected_units[-2]
    return sorted(
        {
            occurrence.mention_id
            for occurrence in occurrences_by_segment[previous.segment_id]
            if occurrence.mention_id not in excluded_ids
            and occurrence.quote_scope == anaphor_scope.scope_id
            and previous.start <= occurrence.start
            and occurrence.end <= previous.end
        }
    )


def candidate_context_unit(
    *,
    selected_units: list[TextUnit],
    candidates: list[str],
    occurrences_by_segment: dict[str, list[NameOccurrence]],
) -> TextUnit | None:
    candidate_set = set(candidates)
    for unit in reversed(selected_units):
        present = {
            occurrence.mention_id
            for occurrence in occurrences_by_segment[unit.segment_id]
            if unit.start <= occurrence.start
            and occurrence.end <= unit.end
            and occurrence.mention_id in candidate_set
        }
        if present == candidate_set:
            return unit
    return None
