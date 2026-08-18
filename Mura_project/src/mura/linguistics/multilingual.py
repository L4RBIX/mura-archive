from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from mura.domain.models import PersonMention, RelationshipClaim, RelationshipRole, RelationshipType
from mura.linguistics import english, kazakh, russian
from mura.linguistics.common import ScriptBucket, detect_script, normalize_text, tokenize


class _Frame(Protocol):
    @property
    def relationship_type(self) -> RelationshipType: ...

    @property
    def possessor_role(self) -> RelationshipRole: ...

    @property
    def relative_role(self) -> RelationshipRole: ...


class _Signal(Protocol):
    @property
    def relationship_type(self) -> RelationshipType: ...

    @property
    def subject_mention_id(self) -> str: ...

    @property
    def subject_role(self) -> RelationshipRole: ...

    @property
    def object_mention_id(self) -> str: ...

    @property
    def object_role(self) -> RelationshipRole: ...

    @property
    def source_surface(self) -> str: ...

    @property
    def rule_id(self) -> str: ...


@dataclass(frozen=True)
class LinguisticNameMatch:
    language: str
    surface: str
    token: str
    start: int
    end: int
    exact: bool
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LinguisticAnchorMatch:
    language: str
    surface: str
    start: int
    end: int
    anchor_kind: str
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LinguisticMarkerMatch:
    language: str
    surface: str
    start: int
    end: int
    marker_type: str
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LinguisticRelationshipSignal:
    language: str
    relationship_type: RelationshipType
    subject_mention_id: str
    subject_role: RelationshipRole
    object_mention_id: str
    object_role: RelationshipRole
    source_surface: str
    rule_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "language": self.language,
            "relationship_type": self.relationship_type.value,
            "subject_mention_id": self.subject_mention_id,
            "subject_role": self.subject_role.value,
            "object_mention_id": self.object_mention_id,
            "object_role": self.object_role.value,
            "source_surface": self.source_surface,
            "rule_id": self.rule_id,
        }


_NameFinder = Callable[[str, str], list[Any]]
_KAZAKH_CONTEXT_TOKENS = frozenset(
    {
        "мен",
        "менің",
        "біз",
        "біздің",
        "ол",
        "оның",
        "олар",
        "олардың",
        "және",
        "үйленді",
        "әкем",
        "анам",
        "шешем",
        "ұлым",
        "ұлымыз",
        "қызым",
        "қызымыз",
        "балам",
        "баламыз",
        "ағам",
        "әпкем",
        "інім",
        "сіңлім",
        "қарындасым",
        "әйелім",
        "күйеуім",
        "әкесі",
        "анасы",
        "шешесі",
        "ұлы",
        "қызы",
        "баласы",
        "ағасы",
        "әпкесі",
        "інісі",
        "сіңлісі",
        "қарындасы",
        "әйелі",
        "күйеуі",
    }
)
_KAZAKH_SPECIFIC_CHARACTERS = frozenset("әғқңөұүһі")


def _person_surfaces(person: PersonMention) -> list[str]:
    values = [person.name, *person.aliases]
    values.extend(variant.surface for variant in person.name_variants)
    return list(dict.fromkeys(value for value in values if value))


def _text_prefers_kazakh(text: str) -> bool:
    normalized = normalize_text(text)
    if set(normalized).intersection(_KAZAKH_SPECIFIC_CHARACTERS):
        return True
    return any(token.normalized in _KAZAKH_CONTEXT_TOKENS for token in tokenize(text))


def _name_finders(text: str, surface: str) -> tuple[tuple[str, _NameFinder], ...]:
    script = detect_script(surface)
    if script is ScriptBucket.LATIN:
        return (("en", english.find_known_name_matches),)
    if script is ScriptBucket.CYRILLIC:
        if _text_prefers_kazakh(text):
            return (("kk", kazakh.find_known_name_matches),)
        return (("ru", russian.find_known_name_matches),)
    return (
        ("kk", kazakh.find_known_name_matches),
        ("ru", russian.find_known_name_matches),
        ("en", english.find_known_name_matches),
    )


def find_known_name_matches(text: str, surface: str) -> list[LinguisticNameMatch]:
    matches: list[LinguisticNameMatch] = []
    for language, finder in _name_finders(text, surface):
        for candidate in finder(text, surface):
            matches.append(
                LinguisticNameMatch(
                    language=language,
                    surface=candidate.surface,
                    token=candidate.token,
                    start=candidate.start,
                    end=candidate.end,
                    exact=candidate.exact,
                    rule_id=candidate.rule_id,
                )
            )
    unique: dict[tuple[str, int, int, str], LinguisticNameMatch] = {}
    for unified_match in matches:
        key = (
            unified_match.language,
            unified_match.start,
            unified_match.end,
            unified_match.rule_id,
        )
        unique.setdefault(key, unified_match)
    return list(unique.values())


def contains_known_name_surface(text: str, surface: str) -> bool:
    return bool(find_known_name_matches(text, surface))


def find_speaker_anchor_matches(text: str) -> list[LinguisticAnchorMatch]:
    matches: list[LinguisticAnchorMatch] = []
    for language, finder in (
        ("kk", kazakh.find_speaker_anchor_matches),
        ("ru", russian.find_speaker_anchor_matches),
        ("en", english.find_speaker_anchor_matches),
    ):
        for candidate in finder(text):
            matches.append(
                LinguisticAnchorMatch(
                    language=language,
                    surface=candidate.surface,
                    start=candidate.start,
                    end=candidate.end,
                    anchor_kind=candidate.anchor_kind,
                    rule_id=candidate.rule_id,
                )
            )
    unique: dict[tuple[str, int, int, str], LinguisticAnchorMatch] = {}
    for unified_match in matches:
        key = (
            unified_match.language,
            unified_match.start,
            unified_match.end,
            unified_match.rule_id,
        )
        unique.setdefault(key, unified_match)
    return list(unique.values())


def _convert_signal(language: str, signal: _Signal) -> LinguisticRelationshipSignal:
    return LinguisticRelationshipSignal(
        language=language,
        relationship_type=signal.relationship_type,
        subject_mention_id=signal.subject_mention_id,
        subject_role=signal.subject_role,
        object_mention_id=signal.object_mention_id,
        object_role=signal.object_role,
        source_surface=signal.source_surface,
        rule_id=signal.rule_id,
    )


def _canonical_signal(
    *,
    language: str,
    possessor_id: str,
    relative_id: str,
    frame: _Frame,
    source_surface: str,
    rule_id: str,
) -> LinguisticRelationshipSignal:
    parent = RelationshipRole.PARENT
    child = RelationshipRole.CHILD
    older = RelationshipRole.OLDER_SIBLING
    younger = RelationshipRole.YOUNGER_SIBLING
    sibling = RelationshipRole.SIBLING
    spouse = RelationshipRole.SPOUSE

    if frame.relationship_type is RelationshipType.PARENT_CHILD:
        if frame.possessor_role is parent:
            subject_id, subject_role = possessor_id, parent
            object_id, object_role = relative_id, child
        else:
            subject_id, subject_role = relative_id, parent
            object_id, object_role = possessor_id, child
    elif frame.relationship_type is RelationshipType.SIBLING:
        if frame.possessor_role is older:
            subject_id, subject_role = possessor_id, older
            object_id, object_role = relative_id, younger
        elif frame.relative_role is older:
            subject_id, subject_role = relative_id, older
            object_id, object_role = possessor_id, younger
        else:
            subject_id, subject_role = possessor_id, sibling
            object_id, object_role = relative_id, sibling
    else:
        subject_id, subject_role = possessor_id, spouse
        object_id, object_role = relative_id, spouse

    return LinguisticRelationshipSignal(
        language=language,
        relationship_type=frame.relationship_type,
        subject_mention_id=subject_id,
        subject_role=subject_role,
        object_mention_id=object_id,
        object_role=object_role,
        source_surface=source_surface,
        rule_id=rule_id,
    )


def _speaker_mentions(people: list[PersonMention], speaker_name: str) -> list[PersonMention]:
    normalized_speaker = normalize_text(speaker_name)
    return [
        person
        for person in people
        if any(
            normalize_text(surface) == normalized_speaker for surface in _person_surfaces(person)
        )
    ]


def _all_person_matches(
    text: str,
    people: list[PersonMention],
) -> dict[str, list[LinguisticNameMatch]]:
    result: dict[str, list[LinguisticNameMatch]] = {}
    for person in people:
        matches = [
            match
            for surface in _person_surfaces(person)
            for match in find_known_name_matches(text, surface)
        ]
        if matches:
            result[person.mention_id] = matches
    return result


def _unique_nearby_target(
    *,
    start: int,
    end: int,
    matches_by_person: dict[str, list[LinguisticNameMatch]],
    excluded_ids: set[str],
    max_distance: int = 70,
) -> str | None:
    candidate_ids = {
        mention_id
        for mention_id, matches in matches_by_person.items()
        if mention_id not in excluded_ids
        and any(
            match.start >= 0 and min(abs(match.start - end), abs(start - match.end)) <= max_distance
            for match in matches
        )
    }
    return next(iter(candidate_ids)) if len(candidate_ids) == 1 else None


def _mixed_speaker_signals(
    text: str,
    people: list[PersonMention],
    speaker_name: str,
) -> list[LinguisticRelationshipSignal]:
    speakers = _speaker_mentions(people, speaker_name)
    if len(speakers) != 1:
        return []
    speaker = speakers[0]
    anchors = find_speaker_anchor_matches(text)
    matches_by_person = _all_person_matches(text, people)
    kinships = [("ru", item) for item in russian.find_kinship_matches(text)] + [
        ("en", item) for item in english.find_kinship_matches(text)
    ]

    signals: list[LinguisticRelationshipSignal] = []
    for kinship_language, kinship in kinships:
        foreign_anchors = [
            anchor
            for anchor in anchors
            if anchor.language != kinship_language
            and min(abs(anchor.start - kinship.end), abs(kinship.start - anchor.end)) <= 35
        ]
        if not foreign_anchors:
            continue
        target_id = _unique_nearby_target(
            start=kinship.start,
            end=kinship.end,
            matches_by_person=matches_by_person,
            excluded_ids={speaker.mention_id},
        )
        if target_id is None:
            continue
        signals.append(
            _canonical_signal(
                language="mixed",
                possessor_id=speaker.mention_id,
                relative_id=target_id,
                frame=kinship.frame,
                source_surface=kinship.surface,
                rule_id="mixed.relationship.speaker_anchor_kinship.v1",
            )
        )
    return signals


def find_relationship_signals(
    text: str,
    people: list[PersonMention],
    speaker_name: str,
) -> list[LinguisticRelationshipSignal]:
    signals = [
        *(
            _convert_signal("kk", signal)
            for signal in kazakh.find_relationship_signals(text, people, speaker_name)
        ),
        *(
            _convert_signal("ru", signal)
            for signal in russian.find_relationship_signals(text, people, speaker_name)
        ),
        *(
            _convert_signal("en", signal)
            for signal in english.find_relationship_signals(text, people, speaker_name)
        ),
        *_mixed_speaker_signals(text, people, speaker_name),
    ]
    unique: dict[tuple[str, str, str, str, str], LinguisticRelationshipSignal] = {}
    for signal in signals:
        key = (
            signal.relationship_type.value,
            signal.subject_mention_id,
            signal.subject_role.value,
            signal.object_mention_id,
            signal.object_role.value,
        )
        existing = unique.get(key)
        if existing is None or existing.language == "mixed":
            unique[key] = signal
    return list(unique.values())


def find_third_person_possessive_markers(text: str) -> list[LinguisticMarkerMatch]:
    matches: list[LinguisticMarkerMatch] = []
    for language, finder in (
        ("ru", russian.find_third_person_possessive_markers),
        ("en", english.find_third_person_possessive_markers),
    ):
        for match in finder(text):
            matches.append(
                LinguisticMarkerMatch(
                    language=language,
                    surface=match.surface,
                    start=match.start,
                    end=match.end,
                    marker_type=match.marker_type,
                    rule_id=match.rule_id,
                )
            )

    tokens = tokenize(text)
    kk_possessives = {"оның", "олардың"}
    kk_kinship = {
        "әкесі",
        "анасы",
        "шешесі",
        "ұлы",
        "қызы",
        "баласы",
        "ағасы",
        "әпкесі",
        "інісі",
        "сіңлісі",
        "қарындасы",
        "әйелі",
        "күйеуі",
    }
    for index, token in enumerate(tokens):
        if token.normalized not in kk_possessives:
            continue
        window = tokens[index + 1 : index + 5]
        if not any(item.normalized in kk_kinship for item in window):
            continue
        matches.append(
            LinguisticMarkerMatch(
                language="kk",
                surface=token.surface,
                start=token.start,
                end=token.end,
                marker_type="third_person_possessive",
                rule_id="kk.coreference.third_person_possessive_guard.v1",
            )
        )
    return matches


def find_uncertainty_markers(text: str) -> list[LinguisticMarkerMatch]:
    matches: list[LinguisticMarkerMatch] = []
    for language, finder in (
        ("kk", kazakh.find_uncertainty_markers),
        ("ru", russian.find_uncertainty_markers),
        ("en", english.find_uncertainty_markers),
    ):
        for match in finder(text):
            matches.append(
                LinguisticMarkerMatch(
                    language=language,
                    surface=match.surface,
                    start=getattr(match, "start", -1),
                    end=getattr(match, "end", -1),
                    marker_type=match.marker_type,
                    rule_id=match.rule_id,
                )
            )
    return matches


def signal_matches_relationship(
    signal: LinguisticRelationshipSignal,
    relationship: RelationshipClaim,
) -> bool:
    if signal.relationship_type is not relationship.relationship_type:
        return False
    if signal.relationship_type is RelationshipType.SPOUSE:
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
