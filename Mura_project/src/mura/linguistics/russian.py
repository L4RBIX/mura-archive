from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mura.domain.models import PersonMention, RelationshipRole, RelationshipType
from mura.linguistics.common import TextToken, normalize_text, tokenize


@dataclass(frozen=True)
class RussianNameMatch:
    surface: str
    token: str
    normalized_token: str
    start: int
    end: int
    grammatical_case: str
    exact: bool
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RussianSpeakerAnchorMatch:
    surface: str
    start: int
    end: int
    anchor_kind: str
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RussianMarkerMatch:
    surface: str
    start: int
    end: int
    marker_type: str
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KinshipFrame:
    relationship_type: RelationshipType
    possessor_role: RelationshipRole
    relative_role: RelationshipRole


@dataclass(frozen=True)
class RussianKinshipMatch:
    surface: str
    start: int
    end: int
    frame: KinshipFrame
    rule_id: str


@dataclass(frozen=True)
class RussianRelationshipSignal:
    relationship_type: RelationshipType
    subject_mention_id: str
    subject_role: RelationshipRole
    object_mention_id: str
    object_role: RelationshipRole
    source_surface: str
    rule_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "relationship_type": self.relationship_type.value,
            "subject_mention_id": self.subject_mention_id,
            "subject_role": self.subject_role.value,
            "object_mention_id": self.object_mention_id,
            "object_role": self.object_role.value,
            "source_surface": self.source_surface,
            "rule_id": self.rule_id,
        }


_PARENT = RelationshipRole.PARENT
_CHILD = RelationshipRole.CHILD
_OLDER = RelationshipRole.OLDER_SIBLING
_YOUNGER = RelationshipRole.YOUNGER_SIBLING
_SIBLING = RelationshipRole.SIBLING
_SPOUSE = RelationshipRole.SPOUSE
_PARENT_CHILD = RelationshipType.PARENT_CHILD
_SIBLING_TYPE = RelationshipType.SIBLING
_SPOUSE_TYPE = RelationshipType.SPOUSE


def _frame(
    relationship_type: RelationshipType,
    possessor_role: RelationshipRole,
    relative_role: RelationshipRole,
) -> KinshipFrame:
    return KinshipFrame(relationship_type, possessor_role, relative_role)


_KINSHIP_FRAMES: dict[tuple[str, ...], KinshipFrame] = {
    ("отец",): _frame(_PARENT_CHILD, _CHILD, _PARENT),
    ("папа",): _frame(_PARENT_CHILD, _CHILD, _PARENT),
    ("мать",): _frame(_PARENT_CHILD, _CHILD, _PARENT),
    ("мама",): _frame(_PARENT_CHILD, _CHILD, _PARENT),
    ("сын",): _frame(_PARENT_CHILD, _PARENT, _CHILD),
    ("дочь",): _frame(_PARENT_CHILD, _PARENT, _CHILD),
    ("ребенок",): _frame(_PARENT_CHILD, _PARENT, _CHILD),
    ("ребёнок",): _frame(_PARENT_CHILD, _PARENT, _CHILD),
    ("старший", "брат"): _frame(_SIBLING_TYPE, _YOUNGER, _OLDER),
    ("старшая", "сестра"): _frame(_SIBLING_TYPE, _YOUNGER, _OLDER),
    ("младший", "брат"): _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    ("младшая", "сестра"): _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    ("брат",): _frame(_SIBLING_TYPE, _SIBLING, _SIBLING),
    ("сестра",): _frame(_SIBLING_TYPE, _SIBLING, _SIBLING),
    ("жена",): _frame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
    ("муж",): _frame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
}

_FIRST_PERSON_FORMS = frozenset(
    (
        "мой моя мое моё мои моего моей моему моем моём моим моими мою "
        "наш наша наше наши нашего нашей нашему нашем нашим нашими нашу"
    ).split()
)
_FIRST_PERSON_PHRASES = (("у", "меня"), ("у", "нас"))
_THIRD_PERSON_POSSESSIVES = frozenset({"его", "ее", "её", "их"})
_UNCERTAINTY_MARKERS = (
    "возможно",
    "примерно",
    "кажется",
    "наверное",
    "если не ошибаюсь",
    "точно не помню",
)


def _person_surfaces(person: PersonMention) -> list[str]:
    values = [person.name, *person.aliases]
    values.extend(variant.surface for variant in person.name_variants)
    return list(dict.fromkeys(value for value in values if value))


def _single_token_forms(surface: str) -> dict[str, str]:
    base = normalize_text(surface)
    if not base or " " in base:
        return {}
    forms = {base: "nominative"}
    if len(base) < 3:
        return forms

    last = base[-1]
    stem = base[:-1]
    if last == "а":
        genitive = "и" if stem[-1:] in "гкхжчшщц" else "ы"
        forms.update(
            {
                stem + genitive: "genitive",
                stem + "е": "dative_or_prepositional",
                stem + "у": "accusative",
                stem + "ой": "instrumental",
                stem + "ою": "instrumental",
            }
        )
    elif last == "я":
        forms.update(
            {
                stem + "и": "genitive",
                stem + "е": "dative_or_prepositional",
                stem + "ю": "accusative",
                stem + "ей": "instrumental",
                stem + "ею": "instrumental",
            }
        )
    elif last == "й":
        forms.update(
            {
                stem + "я": "genitive",
                stem + "ю": "dative",
                stem + "ем": "instrumental",
                stem + "е": "prepositional",
            }
        )
    elif last not in "аеёиоуыэюяь":
        forms.update(
            {
                base + "а": "genitive",
                base + "у": "dative",
                base + "ом": "instrumental",
                base + "е": "prepositional",
            }
        )
    return forms


def find_known_name_matches(text: str, surface: str) -> list[RussianNameMatch]:
    normalized_surface = normalize_text(surface)
    if not normalized_surface:
        return []
    if " " in normalized_surface:
        normalized_text = normalize_text(text)
        if f" {normalized_surface} " not in f" {normalized_text} ":
            return []
        return [
            RussianNameMatch(
                surface=surface,
                token=surface,
                normalized_token=normalized_surface,
                start=-1,
                end=-1,
                grammatical_case="nominative",
                exact=True,
                rule_id="ru.name.exact_phrase.v1",
            )
        ]

    forms = _single_token_forms(surface)
    matches: list[RussianNameMatch] = []
    for token in tokenize(text):
        grammatical_case = forms.get(token.normalized)
        if grammatical_case is None:
            continue
        exact = grammatical_case == "nominative"
        matches.append(
            RussianNameMatch(
                surface=surface,
                token=token.surface,
                normalized_token=token.normalized,
                start=token.start,
                end=token.end,
                grammatical_case=grammatical_case,
                exact=exact,
                rule_id="ru.name.exact.v1" if exact else "ru.name.audited_inflection.v1",
            )
        )
    return matches


def contains_known_name_surface(text: str, surface: str) -> bool:
    return bool(find_known_name_matches(text, surface))


def find_speaker_anchor_matches(text: str) -> list[RussianSpeakerAnchorMatch]:
    tokens = tokenize(text)
    matches: list[RussianSpeakerAnchorMatch] = []
    for index, token in enumerate(tokens):
        if token.normalized in _FIRST_PERSON_FORMS:
            matches.append(
                RussianSpeakerAnchorMatch(
                    surface=token.surface,
                    start=token.start,
                    end=token.end,
                    anchor_kind="first_person_possessive",
                    rule_id="ru.speaker.possessive_pronoun.v1",
                )
            )
        for phrase in _FIRST_PERSON_PHRASES:
            size = len(phrase)
            if tuple(item.normalized for item in tokens[index : index + size]) != phrase:
                continue
            matches.append(
                RussianSpeakerAnchorMatch(
                    surface=" ".join(item.surface for item in tokens[index : index + size]),
                    start=token.start,
                    end=tokens[index + size - 1].end,
                    anchor_kind="first_person_have_frame",
                    rule_id="ru.speaker.u_menya_frame.v1",
                )
            )
    return matches


def find_kinship_matches(text: str) -> list[RussianKinshipMatch]:
    tokens = tokenize(text)
    matches: list[RussianKinshipMatch] = []
    for index, token in enumerate(tokens):
        for phrase, frame in sorted(_KINSHIP_FRAMES.items(), key=lambda item: -len(item[0])):
            size = len(phrase)
            window = tokens[index : index + size]
            if tuple(item.normalized for item in window) != phrase:
                continue
            matches.append(
                RussianKinshipMatch(
                    surface=" ".join(item.surface for item in window),
                    start=token.start,
                    end=window[-1].end,
                    frame=frame,
                    rule_id="ru.kinship.audited_lexeme.v1",
                )
            )
            break
    return matches


def _person_name_matches(
    text: str,
    people: list[PersonMention],
) -> dict[str, list[RussianNameMatch]]:
    result: dict[str, list[RussianNameMatch]] = {}
    for person in people:
        matches = [
            match
            for surface in _person_surfaces(person)
            for match in find_known_name_matches(text, surface)
        ]
        if matches:
            result[person.mention_id] = matches
    return result


def _speaker_mentions(people: list[PersonMention], speaker_name: str) -> list[PersonMention]:
    normalized_speaker = normalize_text(speaker_name)
    return [
        person
        for person in people
        if any(
            normalize_text(surface) == normalized_speaker for surface in _person_surfaces(person)
        )
    ]


def _unique_nearby_target(
    *,
    anchor_start: int,
    anchor_end: int,
    matches_by_person: dict[str, list[RussianNameMatch]],
    excluded_ids: set[str],
    max_distance: int = 70,
) -> str | None:
    candidate_ids = {
        mention_id
        for mention_id, matches in matches_by_person.items()
        if mention_id not in excluded_ids
        and any(
            match.start >= 0
            and min(abs(match.start - anchor_end), abs(anchor_start - match.end)) <= max_distance
            for match in matches
        )
    }
    return next(iter(candidate_ids)) if len(candidate_ids) == 1 else None


def _canonical_signal(
    *,
    possessor_id: str,
    relative_id: str,
    frame: KinshipFrame,
    source_surface: str,
    rule_id: str,
) -> RussianRelationshipSignal:
    if frame.relationship_type is _PARENT_CHILD:
        if frame.possessor_role is _PARENT:
            subject_id, subject_role = possessor_id, _PARENT
            object_id, object_role = relative_id, _CHILD
        else:
            subject_id, subject_role = relative_id, _PARENT
            object_id, object_role = possessor_id, _CHILD
    elif frame.relationship_type is _SIBLING_TYPE:
        if frame.possessor_role is _OLDER:
            subject_id, subject_role = possessor_id, _OLDER
            object_id, object_role = relative_id, _YOUNGER
        elif frame.relative_role is _OLDER:
            subject_id, subject_role = relative_id, _OLDER
            object_id, object_role = possessor_id, _YOUNGER
        else:
            subject_id, subject_role = possessor_id, _SIBLING
            object_id, object_role = relative_id, _SIBLING
    else:
        subject_id, subject_role = possessor_id, _SPOUSE
        object_id, object_role = relative_id, _SPOUSE
    return RussianRelationshipSignal(
        relationship_type=frame.relationship_type,
        subject_mention_id=subject_id,
        subject_role=subject_role,
        object_mention_id=object_id,
        object_role=object_role,
        source_surface=source_surface,
        rule_id=rule_id,
    )


def _only_separators(text: str, start: int, end: int) -> bool:
    return start <= end and not normalize_text(text[start:end])


def _is_u_possessor_frame(
    text: str,
    tokens: list[TextToken],
    possessor_match: RussianNameMatch,
    kinship: RussianKinshipMatch,
) -> bool:
    if kinship.start <= possessor_match.end:
        return False
    previous_tokens = [token for token in tokens if token.end <= possessor_match.start]
    if not previous_tokens or previous_tokens[-1].normalized != "у":
        return False
    if not _only_separators(text, previous_tokens[-1].end, possessor_match.start):
        return False
    between = normalize_text(text[possessor_match.end : kinship.start])
    return between in {"", "есть"}


def find_relationship_signals(
    text: str,
    people: list[PersonMention],
    speaker_name: str,
) -> list[RussianRelationshipSignal]:
    matches_by_person = _person_name_matches(text, people)
    speakers = _speaker_mentions(people, speaker_name)
    anchors = find_speaker_anchor_matches(text)
    kinships = find_kinship_matches(text)
    signals: list[RussianRelationshipSignal] = []

    if len(speakers) == 1:
        speaker = speakers[0]
        for kinship in kinships:
            nearby_anchor = any(
                min(abs(anchor.start - kinship.end), abs(kinship.start - anchor.end)) <= 35
                for anchor in anchors
            )
            if not nearby_anchor:
                continue
            target_id = _unique_nearby_target(
                anchor_start=kinship.start,
                anchor_end=kinship.end,
                matches_by_person=matches_by_person,
                excluded_ids={speaker.mention_id},
            )
            if target_id is not None:
                signals.append(
                    _canonical_signal(
                        possessor_id=speaker.mention_id,
                        relative_id=target_id,
                        frame=kinship.frame,
                        source_surface=kinship.surface,
                        rule_id="ru.relationship.speaker_possessive_kinship.v1",
                    )
                )

    tokens = tokenize(text)
    for possessor in people:
        possessor_matches = matches_by_person.get(possessor.mention_id, [])
        for possessor_match in possessor_matches:
            for kinship in kinships:
                kinship_before_genitive = (
                    possessor_match.grammatical_case == "genitive"
                    and kinship.end <= possessor_match.start
                    and _only_separators(text, kinship.end, possessor_match.start)
                )
                u_possessor_frame = _is_u_possessor_frame(
                    text,
                    tokens,
                    possessor_match,
                    kinship,
                )
                if not kinship_before_genitive and not u_possessor_frame:
                    continue
                target_id = _unique_nearby_target(
                    anchor_start=kinship.start,
                    anchor_end=kinship.end,
                    matches_by_person=matches_by_person,
                    excluded_ids={possessor.mention_id},
                )
                if target_id is not None:
                    signals.append(
                        _canonical_signal(
                            possessor_id=possessor.mention_id,
                            relative_id=target_id,
                            frame=kinship.frame,
                            source_surface=f"{possessor_match.token} {kinship.surface}",
                            rule_id="ru.relationship.named_genitive_kinship.v1",
                        )
                    )

    unique: dict[tuple[str, str, str, str, str], RussianRelationshipSignal] = {}
    for signal in signals:
        key = (
            signal.relationship_type.value,
            signal.subject_mention_id,
            signal.subject_role.value,
            signal.object_mention_id,
            signal.object_role.value,
        )
        unique.setdefault(key, signal)
    return list(unique.values())


def find_third_person_possessive_markers(text: str) -> list[RussianMarkerMatch]:
    tokens = tokenize(text)
    kinships = find_kinship_matches(text)
    matches: list[RussianMarkerMatch] = []
    for token in tokens:
        if token.normalized not in _THIRD_PERSON_POSSESSIVES:
            continue
        if not any(0 <= kinship.start - token.end <= 24 for kinship in kinships):
            continue
        matches.append(
            RussianMarkerMatch(
                surface=token.surface,
                start=token.start,
                end=token.end,
                marker_type="third_person_possessive",
                rule_id="ru.coreference.third_person_possessive_guard.v1",
            )
        )
    return matches


def find_uncertainty_markers(text: str) -> list[RussianMarkerMatch]:
    normalized = normalize_text(text)
    matches: list[RussianMarkerMatch] = []
    for marker in _UNCERTAINTY_MARKERS:
        normalized_marker = normalize_text(marker)
        if f" {normalized_marker} " not in f" {normalized} ":
            continue
        matches.append(
            RussianMarkerMatch(
                surface=marker,
                start=-1,
                end=-1,
                marker_type="uncertainty",
                rule_id="ru.uncertainty.lexical_marker.v1",
            )
        )
    return matches
