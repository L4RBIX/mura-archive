from __future__ import annotations

from mura.domain.models import PersonMention, RelationshipRole, RelationshipType
from mura.linguistics.common import normalize_text, tokenize
from mura.linguistics.multilingual import LinguisticRelationshipSignal, find_known_name_matches

_COORDINATORS = frozenset({"и", "and"})
_SIBLING_CUES = {
    ("брат", "и", "сестра"): ("ru", "ru.relationship.explicit_sibling_coordination.v2"),
    ("сестра", "и", "брат"): ("ru", "ru.relationship.explicit_sibling_coordination.v2"),
    ("brother", "and", "sister"): ("en", "en.relationship.explicit_sibling_coordination.v1"),
    ("sister", "and", "brother"): ("en", "en.relationship.explicit_sibling_coordination.v1"),
}
_BRIDGE_TOKENS = frozenset({"это", "are", "were"})


def _surfaces(person: PersonMention) -> list[str]:
    values = [person.name, *person.aliases]
    values.extend(item.surface for item in person.name_variants)
    return list(dict.fromkeys(value for value in values if value))


def _name_occurrences(text: str, person: PersonMention) -> list[tuple[int, int]]:
    return sorted(
        {
            (match.start, match.end)
            for surface in _surfaces(person)
            for match in find_known_name_matches(text, surface)
            if match.start >= 0
        }
    )


def find_explicit_sibling_signals(
    text: str,
    people: list[PersonMention],
) -> list[LinguisticRelationshipSignal]:
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
    if any(token.normalized.startswith("двоюрод") for token in tokens):
        return []
    endpoint_ids = [person.mention_id for person in people]
    occurrences = {
        mention_id: _name_occurrences(text, people_by_id[mention_id]) for mention_id in endpoint_ids
    }
    signals: list[LinguisticRelationshipSignal] = []
    for first in occurrences[endpoint_ids[0]]:
        for second in occurrences[endpoint_ids[1]]:
            left, right = sorted((first, second), key=lambda item: (item[0], item[1]))
            between_names = [
                token for token in tokens if left[1] <= token.start and token.end <= right[0]
            ]
            if len(between_names) != 1 or between_names[0].normalized not in _COORDINATORS:
                continue
            following = [token for token in tokens if token.start >= right[1]]
            for index in range(len(following) - 2):
                cue_tokens = following[index : index + 3]
                cue_key = (
                    cue_tokens[0].normalized,
                    cue_tokens[1].normalized,
                    cue_tokens[2].normalized,
                )
                cue_spec = _SIBLING_CUES.get(cue_key)
                if cue_spec is None:
                    continue
                bridge = following[:index]
                if cue_tokens[0].start - right[1] > 80 or any(
                    token.normalized not in _BRIDGE_TOKENS for token in bridge
                ):
                    continue
                language, rule_id = cue_spec
                signals.append(
                    LinguisticRelationshipSignal(
                        language=language,
                        relationship_type=RelationshipType.SIBLING,
                        subject_mention_id=endpoint_ids[0],
                        subject_role=RelationshipRole.SIBLING,
                        object_mention_id=endpoint_ids[1],
                        object_role=RelationshipRole.SIBLING,
                        source_surface=text[left[0] : cue_tokens[-1].end],
                        rule_id=rule_id,
                    )
                )
                break
    return signals
