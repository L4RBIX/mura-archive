from __future__ import annotations

import re
from dataclasses import dataclass

from mura.domain.models import PersonMention, RelationshipType
from mura.linguistics.common import TextToken, normalize_text, tokenize
from mura.linguistics.multilingual import find_known_name_matches

_MAX_POST_CUE_DISTANCE = 140
_MAX_PREFIX_CUE_DISTANCE = 48
_DIRECT_BRIDGE_TOKENS = frozenset(
    {
        "были",
        "был",
        "была",
        "это",
        "уже",
        "давно",
        "сначала",
        "are",
        "were",
        "is",
    }
)
_CONTINUATION_RE = re.compile(
    r",\s*(?:а\s+(?:потом|затем|позже|вскоре)|ал\s+(?:кейін|сосын))\b",
    flags=re.IGNORECASE | re.UNICODE,
)
_COORDINATORS = frozenset({"и", "мен", "және", "and"})
_HARD_UNIT_RE = re.compile(r"[^.!?…;\n]+", flags=re.UNICODE)
_SOFT_BOUNDARY_RE = re.compile(
    r",\s*(а|но|зато|однако|ал|бірақ|but|while|whereas|пока|когда)\b",
    flags=re.IGNORECASE | re.UNICODE,
)
_CONTINUATION_TOKENS = {
    "а": frozenset({"потом", "затем", "позже", "вскоре"}),
    "ал": frozenset({"кейін", "сосын"}),
}
_NEGATIONS = frozenset({"не", "not", "емес"})
_INACTIVE_RELATION_MARKERS = frozenset(
    {
        "раньше",
        "бывшие",
        "бывший",
        "бывшая",
        "развелись",
        "разведены",
        "разведён",
        "разведен",
        "разведена",
        "formerly",
        "divorced",
        "ажырасты",
        "ажырасқан",
    }
)
_RELATION_LABELS = {
    "father": frozenset({"отец", "папа"}),
    "mother": frozenset({"мать", "мама"}),
}


@dataclass(frozen=True)
class _EndpointOccurrence:
    mention_id: str
    start: int
    end: int


@dataclass(frozen=True)
class _CueOccurrence:
    language: str
    start: int
    end: int
    prefix_allowed: bool
    rule_id: str


@dataclass(frozen=True)
class ExplicitPairMatch:
    relationship_type: RelationshipType
    subject_mention_id: str
    object_mention_id: str
    language: str
    rule_id: str
    cue_start: int
    cue_end: int
    pair_start: int
    pair_end: int
    source_surface: str


_CUE_SPECS: tuple[tuple[str, tuple[str, ...], bool, str], ...] = (
    ("ru", ("поженились",), False, "ru.relationship.explicit_spouse_coordination.v2"),
    ("ru", ("поженился",), False, "ru.relationship.explicit_spouse_coordination.v2"),
    ("ru", ("поженилась",), False, "ru.relationship.explicit_spouse_coordination.v2"),
    ("ru", ("женились",), False, "ru.relationship.explicit_spouse_coordination.v2"),
    ("ru", ("женился",), False, "ru.relationship.explicit_spouse_coordination.v2"),
    ("ru", ("женилась",), False, "ru.relationship.explicit_spouse_coordination.v2"),
    ("ru", ("женаты",), False, "ru.relationship.explicit_spouse_coordination.v2"),
    ("ru", ("супруги",), True, "ru.relationship.explicit_spouse_coordination.v2"),
    ("ru", ("мужем", "и", "женой"), False, "ru.relationship.explicit_spouse_coordination.v2"),
    ("ru", ("муж", "и", "жена"), False, "ru.relationship.explicit_spouse_coordination.v2"),
    ("kk", ("үйленді",), False, "kk.relationship.explicit_spouse_coordination.v2"),
    ("kk", ("үйленген",), False, "kk.relationship.explicit_spouse_coordination.v2"),
    ("kk", ("некелесті",), False, "kk.relationship.explicit_spouse_coordination.v2"),
    ("kk", ("жұбайлар",), True, "kk.relationship.explicit_spouse_coordination.v2"),
    ("en", ("married",), False, "en.relationship.explicit_spouse_coordination.v1"),
    ("en", ("spouses",), True, "en.relationship.explicit_spouse_coordination.v1"),
)
_DIRECT_ENDPOINT_SPECS: tuple[tuple[str, tuple[str, ...], int, str], ...] = (
    ("ru", ("вышла", "замуж", "за"), 2, "ru.relationship.explicit_spouse_direct.v1"),
    ("ru", ("женился", "на"), 1, "ru.relationship.explicit_spouse_direct.v1"),
    ("ru", ("женилась", "на"), 1, "ru.relationship.explicit_spouse_direct.v1"),
    ("ru", ("поженился", "с"), 1, "ru.relationship.explicit_spouse_direct.v1"),
    ("ru", ("поженилась", "с"), 1, "ru.relationship.explicit_spouse_direct.v1"),
    ("en", ("married",), 1, "en.relationship.explicit_spouse_direct.v1"),
)


def _surfaces(person: PersonMention) -> list[str]:
    values = [person.name, *person.aliases]
    values.extend(item.surface for item in person.name_variants)
    return list(dict.fromkeys(value for value in values if value))


def _name_occurrences(text: str, person: PersonMention) -> list[_EndpointOccurrence]:
    matches = {
        (match.start, match.end)
        for surface in _surfaces(person)
        for match in find_known_name_matches(text, surface)
        if match.start >= 0
    }
    return [_EndpointOccurrence(person.mention_id, start, end) for start, end in sorted(matches)]


def _label_occurrences(
    people: list[PersonMention], tokens: list[TextToken]
) -> dict[str, list[_EndpointOccurrence]]:
    labels = {normalize_text(person.relation_to_speaker or "") for person in people}
    if labels != {"father", "mother"}:
        return {}
    result: dict[str, list[_EndpointOccurrence]] = {}
    for person in people:
        accepted = _RELATION_LABELS.get(
            normalize_text(person.relation_to_speaker or ""), frozenset()
        )
        matches = [
            _EndpointOccurrence(person.mention_id, token.start, token.end)
            for token in tokens
            if token.normalized in accepted
        ]
        if matches:
            result[person.mention_id] = matches
    return result


def _next_token(tokens: list[TextToken], offset: int) -> TextToken | None:
    return next((token for token in tokens if token.start >= offset), None)


def _clause_spans(text: str, tokens: list[TextToken]) -> list[tuple[int, int, int, int]]:
    spans: list[tuple[int, int, int, int]] = []
    for hard in _HARD_UNIT_RE.finditer(text):
        hard_start, hard_end = hard.span()
        while hard_start < hard_end and text[hard_start].isspace():
            hard_start += 1
        while hard_end > hard_start and text[hard_end - 1].isspace():
            hard_end -= 1
        if hard_start >= hard_end:
            continue
        local = text[hard_start:hard_end]
        split_points: list[tuple[int, int]] = []
        for boundary in _SOFT_BOUNDARY_RE.finditer(local):
            conjunction = normalize_text(boundary.group(1))
            following = _next_token(tokens, hard_start + boundary.end())
            if following is not None and following.normalized in _CONTINUATION_TOKENS.get(
                conjunction, frozenset()
            ):
                continue
            split_points.append((hard_start + boundary.start(), hard_start + boundary.end()))
        current = hard_start
        for boundary_start, boundary_end in split_points:
            if current < boundary_start:
                spans.append((current, boundary_start, hard_start, hard_end))
            current = boundary_end
        if current < hard_end:
            spans.append((current, hard_end, hard_start, hard_end))
    return spans


def _cue_occurrences(tokens: list[TextToken]) -> list[_CueOccurrence]:
    matches: list[_CueOccurrence] = []
    for language, values, prefix_allowed, rule_id in _CUE_SPECS:
        size = len(values)
        for index in range(len(tokens) - size + 1):
            selected = tokens[index : index + size]
            if tuple(token.normalized for token in selected) != values:
                continue
            matches.append(
                _CueOccurrence(
                    language=language,
                    start=selected[0].start,
                    end=selected[-1].end,
                    prefix_allowed=prefix_allowed,
                    rule_id=rule_id,
                )
            )
    return matches


def _is_negated(tokens: list[TextToken], cue: _CueOccurrence) -> bool:
    cue_indexes = [
        index
        for index, token in enumerate(tokens)
        if token.start < cue.end and token.end > cue.start
    ]
    if not cue_indexes:
        return False
    first, last = cue_indexes[0], cue_indexes[-1]
    nearby = tokens[max(0, first - 3) : first] + tokens[last + 1 : last + 3]
    return any(token.normalized in _NEGATIONS for token in nearby)


def _contains_inactive_marker(tokens: list[TextToken]) -> bool:
    return any(token.normalized in _INACTIVE_RELATION_MARKERS for token in tokens)


def _tokens_between(tokens: list[TextToken], start: int, end: int) -> list[TextToken]:
    return [token for token in tokens if start <= token.start and token.end <= end]


def _has_coordinator_between(
    tokens: list[TextToken], left: _EndpointOccurrence, right: _EndpointOccurrence
) -> bool:
    between = _tokens_between(tokens, left.end, right.start)
    return len(between) == 1 and between[0].normalized in _COORDINATORS


def _looks_like_list_member(text: str, clause_start: int, left: _EndpointOccurrence) -> bool:
    prefix = text[clause_start : left.start]
    return bool(re.search(r",\s*$", prefix, flags=re.UNICODE))


def _post_pair_bridge_supported(
    text: str,
    tokens: list[TextToken],
    right: _EndpointOccurrence,
    cue: _CueOccurrence,
) -> bool:
    if cue.start < right.end or cue.start - right.end > _MAX_POST_CUE_DISTANCE:
        return False
    bridge = text[right.end : cue.start]
    continuation = _CONTINUATION_RE.search(bridge)
    if continuation is not None:
        tail_start = right.end + continuation.end()
        tail_tokens = _tokens_between(tokens, tail_start, cue.start)
        return all(token.normalized in _DIRECT_BRIDGE_TOKENS for token in tail_tokens)
    bridge_tokens = _tokens_between(tokens, right.end, cue.start)
    return all(token.normalized in _DIRECT_BRIDGE_TOKENS for token in bridge_tokens)


def _pair_and_cue_are_local(
    *,
    text: str,
    tokens: list[TextToken],
    left: _EndpointOccurrence,
    right: _EndpointOccurrence,
    cue: _CueOccurrence,
) -> bool:
    if cue.start >= right.end:
        return _post_pair_bridge_supported(text, tokens, right, cue)
    if cue.prefix_allowed and cue.end <= left.start:
        bridge_tokens = _tokens_between(tokens, cue.end, left.start)
        return left.start - cue.end <= _MAX_PREFIX_CUE_DISTANCE and not bridge_tokens
    return False


def _direct_endpoint_cue(
    tokens: list[TextToken],
    left: _EndpointOccurrence,
    right: _EndpointOccurrence,
) -> _CueOccurrence | None:
    between = _tokens_between(tokens, left.end, right.start)
    normalized = tuple(token.normalized for token in between)
    for language, pattern, cue_size, rule_id in _DIRECT_ENDPOINT_SPECS:
        if normalized != pattern:
            continue
        return _CueOccurrence(
            language=language,
            start=between[0].start,
            end=between[cue_size - 1].end,
            prefix_allowed=False,
            rule_id=rule_id,
        )
    return None


def _build_match(
    *,
    text: str,
    first_id: str,
    second_id: str,
    left: _EndpointOccurrence,
    right: _EndpointOccurrence,
    cue: _CueOccurrence,
) -> ExplicitPairMatch:
    pair_start, pair_end = left.start, right.end
    source_start = min(pair_start, cue.start)
    source_end = max(pair_end, cue.end)
    return ExplicitPairMatch(
        relationship_type=RelationshipType.SPOUSE,
        subject_mention_id=first_id,
        object_mention_id=second_id,
        language=cue.language,
        rule_id=cue.rule_id,
        cue_start=cue.start,
        cue_end=cue.end,
        pair_start=pair_start,
        pair_end=pair_end,
        source_surface=text[source_start:source_end],
    )


def find_explicit_pair_matches(
    text: str,
    people: list[PersonMention],
) -> list[ExplicitPairMatch]:
    if len(people) != 2:
        return []
    people_by_id = {person.mention_id: person for person in people}
    if len(people_by_id) != 2:
        return []
    normalized_surfaces = [
        {normalize_text(surface) for surface in _surfaces(person) if normalize_text(surface)}
        for person in people
    ]
    if normalized_surfaces[0].intersection(normalized_surfaces[1]):
        return []

    tokens = tokenize(text)
    occurrences = {person.mention_id: _name_occurrences(text, person) for person in people}
    label_occurrences = _label_occurrences(people, tokens)
    for mention_id, values in label_occurrences.items():
        occurrences[mention_id] = [*occurrences.get(mention_id, []), *values]
    if any(not occurrences.get(mention_id) for mention_id in people_by_id):
        return []

    cues = _cue_occurrences(tokens)
    matches: dict[tuple[str, str, int, int, str], ExplicitPairMatch] = {}
    endpoint_ids = sorted(people_by_id)
    for clause_start, clause_end, hard_start, hard_end in _clause_spans(text, tokens):
        hard_tokens = _tokens_between(tokens, hard_start, hard_end)
        if _contains_inactive_marker(hard_tokens):
            continue
        first_id, second_id = endpoint_ids
        first_occurrences = [
            item
            for item in occurrences[first_id]
            if clause_start <= item.start and item.end <= clause_end
        ]
        second_occurrences = [
            item
            for item in occurrences[second_id]
            if clause_start <= item.start and item.end <= clause_end
        ]
        for first in first_occurrences:
            for second in second_occurrences:
                left, right = sorted((first, second), key=lambda item: (item.start, item.end))
                if left.end > right.start or _looks_like_list_member(text, clause_start, left):
                    continue
                direct_cue = _direct_endpoint_cue(tokens, left, right)
                if direct_cue is not None and not _is_negated(tokens, direct_cue):
                    match = _build_match(
                        text=text,
                        first_id=first_id,
                        second_id=second_id,
                        left=left,
                        right=right,
                        cue=direct_cue,
                    )
                    key = (
                        first_id,
                        second_id,
                        direct_cue.start,
                        direct_cue.end,
                        direct_cue.rule_id,
                    )
                    matches.setdefault(key, match)
        clause_cues = [cue for cue in cues if clause_start <= cue.start and cue.end <= clause_end]
        for cue in clause_cues:
            if _is_negated(tokens, cue):
                continue
            for first in first_occurrences:
                for second in second_occurrences:
                    left, right = sorted((first, second), key=lambda item: (item.start, item.end))
                    if left.end > right.start:
                        continue
                    if _looks_like_list_member(text, clause_start, left):
                        continue
                    if not _has_coordinator_between(tokens, left, right):
                        continue
                    if not _pair_and_cue_are_local(
                        text=text, tokens=tokens, left=left, right=right, cue=cue
                    ):
                        continue
                    match = _build_match(
                        text=text,
                        first_id=first_id,
                        second_id=second_id,
                        left=left,
                        right=right,
                        cue=cue,
                    )
                    key = (first_id, second_id, cue.start, cue.end, cue.rule_id)
                    matches.setdefault(key, match)
    return sorted(
        matches.values(),
        key=lambda item: (item.cue_start, item.pair_start, item.subject_mention_id),
    )
