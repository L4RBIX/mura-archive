from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mura.domain.models import (
    PersonMention,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
)
from mura.linguistics.common import normalize_text, tokenize

_CASE_SUFFIXES = frozenset(
    (
        "ның нің дың дің тың тің ға ге қа ке да де та те "
        "дан ден тан тен нан нен ды ді ты ті мен бен пен"
    ).split()
)
_GENITIVE_SUFFIXES = frozenset("ның нің дың дің тың тің".split())
_UNAMBIGUOUS_FIRST_PERSON_FORMS = frozenset(
    "менің маған мені менде менен біз біздің бізге бізді бізде бізден".split()
)
_FIRST_PERSON_LEFT_CONTEXT = frozenset({"ал", "бірақ", "сосын", "кейін"})
_UNCERTAINTY_MARKERS = (
    "мүмкін",
    "шамамен",
    "сияқты",
    "секілді",
    "нақты емес",
    "қателеспесем",
    "меніңше",
    "дәл есімде жоқ",
)


@dataclass(frozen=True)
class KazakhNameMatch:
    surface: str
    token: str
    normalized_token: str
    start: int
    end: int
    suffix: str | None
    exact: bool
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SpeakerAnchorMatch:
    surface: str
    start: int
    end: int
    anchor_kind: str
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarkerMatch:
    surface: str
    marker_type: str
    rule_id: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class KinshipFrame:
    relationship_type: RelationshipType
    possessor_role: RelationshipRole
    relative_role: RelationshipRole


@dataclass(frozen=True)
class KazakhRelationshipSignal:
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


def _frame(
    relationship_type: RelationshipType,
    possessor_role: RelationshipRole,
    relative_role: RelationshipRole,
) -> KinshipFrame:
    return KinshipFrame(relationship_type, possessor_role, relative_role)


_PARENT = RelationshipRole.PARENT
_CHILD = RelationshipRole.CHILD
_OLDER = RelationshipRole.OLDER_SIBLING
_YOUNGER = RelationshipRole.YOUNGER_SIBLING
_SIBLING = RelationshipRole.SIBLING
_SPOUSE = RelationshipRole.SPOUSE
_PARENT_CHILD = RelationshipType.PARENT_CHILD
_SIBLING_TYPE = RelationshipType.SIBLING
_SPOUSE_TYPE = RelationshipType.SPOUSE

# Only locally unambiguous kinship lexemes are allowed to prove graph edges. Terms such as
# "жолдас" (spouse/companion) and "бауыр" (sibling/relative/affectionate address) stay outside
# this deterministic rule pack and require contextual reasoning or review.
_SPEAKER_KINSHIP_FRAMES: dict[str, KinshipFrame] = {
    "әкем": _frame(_PARENT_CHILD, _CHILD, _PARENT),
    "анам": _frame(_PARENT_CHILD, _CHILD, _PARENT),
    "шешем": _frame(_PARENT_CHILD, _CHILD, _PARENT),
    "ұлым": _frame(_PARENT_CHILD, _PARENT, _CHILD),
    "ұлымыз": _frame(_PARENT_CHILD, _PARENT, _CHILD),
    "қызым": _frame(_PARENT_CHILD, _PARENT, _CHILD),
    "қызымыз": _frame(_PARENT_CHILD, _PARENT, _CHILD),
    "балам": _frame(_PARENT_CHILD, _PARENT, _CHILD),
    "баламыз": _frame(_PARENT_CHILD, _PARENT, _CHILD),
    "ағам": _frame(_SIBLING_TYPE, _YOUNGER, _OLDER),
    "әпкем": _frame(_SIBLING_TYPE, _YOUNGER, _OLDER),
    "інім": _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    "сіңлім": _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    "қарындасым": _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    "әйелім": _frame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
    "күйеуім": _frame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
}

_NAMED_POSSESSOR_FRAMES: dict[str, KinshipFrame] = {
    "әкесі": _frame(_PARENT_CHILD, _CHILD, _PARENT),
    "анасы": _frame(_PARENT_CHILD, _CHILD, _PARENT),
    "шешесі": _frame(_PARENT_CHILD, _CHILD, _PARENT),
    "ұлы": _frame(_PARENT_CHILD, _PARENT, _CHILD),
    "қызы": _frame(_PARENT_CHILD, _PARENT, _CHILD),
    "баласы": _frame(_PARENT_CHILD, _PARENT, _CHILD),
    "ағасы": _frame(_SIBLING_TYPE, _YOUNGER, _OLDER),
    "әпкесі": _frame(_SIBLING_TYPE, _YOUNGER, _OLDER),
    "інісі": _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    "сіңлісі": _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    "қарындасы": _frame(_SIBLING_TYPE, _OLDER, _YOUNGER),
    "әйелі": _frame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
    "күйеуі": _frame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
}


def _person_surfaces(person: PersonMention) -> list[str]:
    values = [person.name, *person.aliases]
    values.extend(variant.surface for variant in person.name_variants)
    return list(dict.fromkeys(value for value in values if value))


def _split_known_name_token(token: str, surface: str) -> tuple[bool, str | None]:
    normalized_surface = normalize_text(surface)
    if not normalized_surface or " " in normalized_surface:
        return False, None
    if token == normalized_surface:
        return True, None
    if len(normalized_surface) < 3 or not token.startswith(normalized_surface):
        return False, None
    suffix = token[len(normalized_surface) :]
    return suffix in _CASE_SUFFIXES, suffix if suffix in _CASE_SUFFIXES else None


def find_known_name_matches(text: str, surface: str) -> list[KazakhNameMatch]:
    normalized_surface = normalize_text(surface)
    if not normalized_surface:
        return []

    if " " in normalized_surface:
        normalized_text = normalize_text(text)
        if f" {normalized_surface} " not in f" {normalized_text} ":
            return []
        return [
            KazakhNameMatch(
                surface=surface,
                token=surface,
                normalized_token=normalized_surface,
                start=-1,
                end=-1,
                suffix=None,
                exact=True,
                rule_id="kk.name.exact_phrase.v1",
            )
        ]

    matches: list[KazakhNameMatch] = []
    for token in tokenize(text):
        matched, suffix = _split_known_name_token(token.normalized, normalized_surface)
        if matched:
            matches.append(
                KazakhNameMatch(
                    surface=surface,
                    token=token.surface,
                    normalized_token=token.normalized,
                    start=token.start,
                    end=token.end,
                    suffix=suffix,
                    exact=suffix is None,
                    rule_id=(
                        "kk.name.exact.v1" if suffix is None else "kk.name.known_case_suffix.v1"
                    ),
                )
            )
    return matches


def contains_known_name_surface(text: str, surface: str) -> bool:
    return bool(find_known_name_matches(text, surface))


def _matches_possessed_form(token: str, base: str) -> bool:
    if token == base:
        return True
    return token.startswith(base) and token[len(base) :] in _CASE_SUFFIXES


def find_speaker_anchor_matches(text: str) -> list[SpeakerAnchorMatch]:
    tokens = tokenize(text)
    matches: list[SpeakerAnchorMatch] = []
    for index, token in enumerate(tokens):
        if token.normalized in _UNAMBIGUOUS_FIRST_PERSON_FORMS:
            matches.append(
                SpeakerAnchorMatch(
                    surface=token.surface,
                    start=token.start,
                    end=token.end,
                    anchor_kind="first_person",
                    rule_id="kk.speaker.explicit_pronoun.v1",
                )
            )
        elif token.normalized == "мен" and (
            index == 0 or tokens[index - 1].normalized in _FIRST_PERSON_LEFT_CONTEXT
        ):
            matches.append(
                SpeakerAnchorMatch(
                    surface=token.surface,
                    start=token.start,
                    end=token.end,
                    anchor_kind="first_person",
                    rule_id="kk.speaker.bare_pronoun_context.v1",
                )
            )

        for base in _SPEAKER_KINSHIP_FRAMES:
            if _matches_possessed_form(token.normalized, base):
                matches.append(
                    SpeakerAnchorMatch(
                        surface=token.surface,
                        start=token.start,
                        end=token.end,
                        anchor_kind="possessed_kinship",
                        rule_id="kk.speaker.possessive_kinship.v1",
                    )
                )
                break
    return matches


def has_speaker_anchor(text: str) -> bool:
    return bool(find_speaker_anchor_matches(text))


def find_uncertainty_markers(text: str) -> list[MarkerMatch]:
    normalized = normalize_text(text)
    return [
        MarkerMatch(
            surface=marker,
            marker_type="uncertainty",
            rule_id="kk.uncertainty.lexical_marker.v1",
        )
        for marker in _UNCERTAINTY_MARKERS
        if f" {normalize_text(marker)} " in f" {normalized} "
    ]


def _person_name_matches(
    text: str,
    people: list[PersonMention],
) -> dict[str, list[KazakhNameMatch]]:
    result: dict[str, list[KazakhNameMatch]] = {}
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
    matches_by_person: dict[str, list[KazakhNameMatch]],
    excluded_ids: set[str],
    max_distance: int = 80,
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
) -> KazakhRelationshipSignal:
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

    return KazakhRelationshipSignal(
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
) -> list[KazakhRelationshipSignal]:
    tokens = tokenize(text)
    matches_by_person = _person_name_matches(text, people)
    speakers = _speaker_mentions(people, speaker_name)
    signals: list[KazakhRelationshipSignal] = []

    if len(speakers) == 1:
        speaker = speakers[0]
        for token in tokens:
            for base, speaker_frame in _SPEAKER_KINSHIP_FRAMES.items():
                if not _matches_possessed_form(token.normalized, base):
                    continue
                target_id = _unique_nearby_target(
                    anchor_start=token.start,
                    anchor_end=token.end,
                    matches_by_person=matches_by_person,
                    excluded_ids={speaker.mention_id},
                )
                if target_id is not None:
                    signals.append(
                        _canonical_signal(
                            possessor_id=speaker.mention_id,
                            relative_id=target_id,
                            frame=speaker_frame,
                            source_surface=token.surface,
                            rule_id="kk.relationship.speaker_possessive_kinship.v1",
                        )
                    )
                break

    for possessor in people:
        possessor_matches = matches_by_person.get(possessor.mention_id, [])
        genitive_matches = [
            match for match in possessor_matches if match.suffix in _GENITIVE_SUFFIXES
        ]
        for possessor_match in genitive_matches:
            following_tokens = [
                token
                for token in tokens
                if token.start >= possessor_match.end and token.start - possessor_match.end <= 40
            ]
            for token in following_tokens[:4]:
                named_frame = _NAMED_POSSESSOR_FRAMES.get(token.normalized)
                if named_frame is None:
                    continue
                target_id = _unique_nearby_target(
                    anchor_start=token.start,
                    anchor_end=token.end,
                    matches_by_person=matches_by_person,
                    excluded_ids={possessor.mention_id},
                )
                if target_id is not None:
                    signals.append(
                        _canonical_signal(
                            possessor_id=possessor.mention_id,
                            relative_id=target_id,
                            frame=named_frame,
                            source_surface=f"{possessor_match.token} {token.surface}",
                            rule_id="kk.relationship.named_genitive_kinship.v1",
                        )
                    )
                break

    unique: dict[tuple[str, str, str, str, str], KazakhRelationshipSignal] = {}
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


def signal_matches_relationship(
    signal: KazakhRelationshipSignal,
    relationship: RelationshipClaim,
) -> bool:
    if signal.relationship_type is not relationship.relationship_type:
        return False
    if signal.relationship_type is _SPOUSE_TYPE:
        return {
            signal.subject_mention_id,
            signal.object_mention_id,
        } == {
            relationship.subject_mention_id,
            relationship.object_mention_id,
        }
    return (
        signal.subject_mention_id == relationship.subject_mention_id
        and signal.subject_role is relationship.subject_role
        and signal.object_mention_id == relationship.object_mention_id
        and signal.object_role is relationship.object_role
    )
