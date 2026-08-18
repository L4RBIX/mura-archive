from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mura.domain.models import PersonMention, RelationshipRole, RelationshipType
from mura.linguistics.common import normalize_text, tokenize


@dataclass(frozen=True)
class EnglishNameMatch:
    surface: str
    token: str
    normalized_token: str
    start: int
    end: int
    possessive: bool
    exact: bool
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnglishSpeakerAnchorMatch:
    surface: str
    start: int
    end: int
    anchor_kind: str
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnglishMarkerMatch:
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
class EnglishKinshipMatch:
    surface: str
    start: int
    end: int
    frame: KinshipFrame
    rule_id: str


@dataclass(frozen=True)
class EnglishRelationshipSignal:
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
    ("father",): _frame(_PARENT_CHILD, _CHILD, _PARENT),
    ("dad",): _frame(_PARENT_CHILD, _CHILD, _PARENT),
    ("mother",): _frame(_PARENT_CHILD, _CHILD, _PARENT),
    ("mom",): _frame(_PARENT_CHILD, _CHILD, _PARENT),
    ("mum",): _frame(_PARENT_CHILD, _CHILD, _PARENT),
    ("son",): _frame(_PARENT_CHILD, _PARENT, _CHILD),
    ("daughter",): _frame(_PARENT_CHILD, _PARENT, _CHILD),
    ("child",): _frame(_PARENT_CHILD, _PARENT, _CHILD),
    ("older", "brother"): _frame(_SIBLING_TYPE, _YOUNGER, _OLDER),
    ("older", "sister"): _frame(_SIBLING_TYPE, _YOUNGER, _OLDER),
    ("younger", "brother"): _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    ("younger", "sister"): _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    ("brother",): _frame(_SIBLING_TYPE, _SIBLING, _SIBLING),
    ("sister",): _frame(_SIBLING_TYPE, _SIBLING, _SIBLING),
    ("wife",): _frame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
    ("husband",): _frame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
    ("spouse",): _frame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
}

_FIRST_PERSON_FORMS = frozenset({"my", "our"})
_FIRST_PERSON_HAVE_FRAMES = (("i", "have"), ("we", "have"))
_THIRD_PERSON_POSSESSIVES = frozenset({"his", "her", "their"})
_UNCERTAINTY_MARKERS = (
    "maybe",
    "approximately",
    "about",
    "probably",
    "i think",
    "if i remember correctly",
    "i do not remember exactly",
)


def _person_surfaces(person: PersonMention) -> list[str]:
    values = [person.name, *person.aliases]
    values.extend(variant.surface for variant in person.name_variants)
    return list(dict.fromkeys(value for value in values if value))


def find_known_name_matches(text: str, surface: str) -> list[EnglishNameMatch]:
    normalized_surface = normalize_text(surface)
    if not normalized_surface:
        return []
    tokens = tokenize(text)
    surface_tokens = normalized_surface.split()
    matches: list[EnglishNameMatch] = []
    size = len(surface_tokens)
    for index, token in enumerate(tokens):
        window = tokens[index : index + size]
        if tuple(item.normalized for item in window) != tuple(surface_tokens):
            continue
        possessive = (
            index + size < len(tokens)
            and tokens[index + size].normalized == "s"
            and text[window[-1].end : tokens[index + size].end].lstrip().startswith(("'", "’"))
        )
        matches.append(
            EnglishNameMatch(
                surface=surface,
                token=" ".join(item.surface for item in window),
                normalized_token=normalized_surface,
                start=token.start,
                end=tokens[index + size].end if possessive else window[-1].end,
                possessive=possessive,
                exact=not possessive,
                rule_id="en.name.possessive.v1" if possessive else "en.name.exact.v1",
            )
        )
    return matches


def contains_known_name_surface(text: str, surface: str) -> bool:
    return bool(find_known_name_matches(text, surface))


def find_speaker_anchor_matches(text: str) -> list[EnglishSpeakerAnchorMatch]:
    tokens = tokenize(text)
    matches: list[EnglishSpeakerAnchorMatch] = []
    for index, token in enumerate(tokens):
        if token.normalized in _FIRST_PERSON_FORMS:
            matches.append(
                EnglishSpeakerAnchorMatch(
                    surface=token.surface,
                    start=token.start,
                    end=token.end,
                    anchor_kind="first_person_possessive",
                    rule_id="en.speaker.possessive_pronoun.v1",
                )
            )
        for phrase in _FIRST_PERSON_HAVE_FRAMES:
            size = len(phrase)
            if tuple(item.normalized for item in tokens[index : index + size]) != phrase:
                continue
            matches.append(
                EnglishSpeakerAnchorMatch(
                    surface=" ".join(item.surface for item in tokens[index : index + size]),
                    start=token.start,
                    end=tokens[index + size - 1].end,
                    anchor_kind="first_person_have_frame",
                    rule_id="en.speaker.have_frame.v1",
                )
            )
    return matches


def find_kinship_matches(text: str) -> list[EnglishKinshipMatch]:
    tokens = tokenize(text)
    matches: list[EnglishKinshipMatch] = []
    for index, token in enumerate(tokens):
        for phrase, frame in sorted(_KINSHIP_FRAMES.items(), key=lambda item: -len(item[0])):
            size = len(phrase)
            window = tokens[index : index + size]
            if tuple(item.normalized for item in window) != phrase:
                continue
            matches.append(
                EnglishKinshipMatch(
                    surface=" ".join(item.surface for item in window),
                    start=token.start,
                    end=window[-1].end,
                    frame=frame,
                    rule_id="en.kinship.audited_lexeme.v1",
                )
            )
            break
    return matches


def _person_name_matches(
    text: str,
    people: list[PersonMention],
) -> dict[str, list[EnglishNameMatch]]:
    result: dict[str, list[EnglishNameMatch]] = {}
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
    matches_by_person: dict[str, list[EnglishNameMatch]],
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
) -> EnglishRelationshipSignal:
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
    return EnglishRelationshipSignal(
        relationship_type=frame.relationship_type,
        subject_mention_id=subject_id,
        subject_role=subject_role,
        object_mention_id=object_id,
        object_role=object_role,
        source_surface=source_surface,
        rule_id=rule_id,
    )


def find_relationship_signals(
    text: str,
    people: list[PersonMention],
    speaker_name: str,
) -> list[EnglishRelationshipSignal]:
    matches_by_person = _person_name_matches(text, people)
    speakers = _speaker_mentions(people, speaker_name)
    anchors = find_speaker_anchor_matches(text)
    kinships = find_kinship_matches(text)
    signals: list[EnglishRelationshipSignal] = []

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
                        rule_id="en.relationship.speaker_possessive_kinship.v1",
                    )
                )

    for possessor in people:
        possessor_matches = matches_by_person.get(possessor.mention_id, [])
        for possessor_match in possessor_matches:
            for kinship in kinships:
                normalized_between = normalize_text(text[possessor_match.end : kinship.start])
                possessive_pattern = (
                    possessor_match.possessive and 0 <= kinship.start - possessor_match.end <= 20
                )
                of_pattern = 0 <= possessor_match.start - kinship.end <= 20 and normalize_text(
                    text[kinship.end : possessor_match.start]
                ) in {"of", "of the"}
                have_pattern = (
                    0 <= kinship.start - possessor_match.end <= 30
                    and normalized_between in {"has a", "has an", "has", "have a", "have"}
                )
                if not (possessive_pattern or of_pattern or have_pattern):
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
                            rule_id="en.relationship.named_possessive_kinship.v1",
                        )
                    )

    named_ids = list(matches_by_person)
    normalized = normalize_text(text)
    if len(named_ids) == 2 and any(
        phrase in f" {normalized} "
        for phrase in (" are married ", " got married ", " were married ")
    ):
        signals.append(
            EnglishRelationshipSignal(
                relationship_type=_SPOUSE_TYPE,
                subject_mention_id=named_ids[0],
                subject_role=_SPOUSE,
                object_mention_id=named_ids[1],
                object_role=_SPOUSE,
                source_surface="married",
                rule_id="en.relationship.explicit_married_pair.v1",
            )
        )

    unique: dict[tuple[str, str, str, str, str], EnglishRelationshipSignal] = {}
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


def find_third_person_possessive_markers(text: str) -> list[EnglishMarkerMatch]:
    tokens = tokenize(text)
    kinships = find_kinship_matches(text)
    matches: list[EnglishMarkerMatch] = []
    for token in tokens:
        if token.normalized not in _THIRD_PERSON_POSSESSIVES:
            continue
        if not any(0 <= kinship.start - token.end <= 24 for kinship in kinships):
            continue
        matches.append(
            EnglishMarkerMatch(
                surface=token.surface,
                start=token.start,
                end=token.end,
                marker_type="third_person_possessive",
                rule_id="en.coreference.third_person_possessive_guard.v1",
            )
        )
    return matches


def find_uncertainty_markers(text: str) -> list[EnglishMarkerMatch]:
    normalized = normalize_text(text)
    matches: list[EnglishMarkerMatch] = []
    for marker in _UNCERTAINTY_MARKERS:
        normalized_marker = normalize_text(marker)
        if f" {normalized_marker} " not in f" {normalized} ":
            continue
        matches.append(
            EnglishMarkerMatch(
                surface=marker,
                start=-1,
                end=-1,
                marker_type="uncertainty",
                rule_id="en.uncertainty.lexical_marker.v1",
            )
        )
    return matches
