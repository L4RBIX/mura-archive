from __future__ import annotations

import re
from dataclasses import dataclass

from mura.domain.models import (
    PersonMention,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    TranscriptEnvelope,
)
from mura.explicit_pair_grounding import find_explicit_pair_matches
from mura.explicit_sibling_grounding import find_explicit_sibling_signals
from mura.linguistics import kazakh, russian
from mura.linguistics.common import TextToken, normalize_text, tokenize
from mura.linguistics.multilingual import (
    LinguisticRelationshipSignal,
    find_relationship_signals,
    find_speaker_anchor_matches,
    find_third_person_possessive_markers,
)

_MAX_CONTEXT_SENTENCES = 2
_MAX_CONTEXT_CHARS = 420
_SENTENCE_RE = re.compile(r"[^.!?…;\n]+(?:[.!?…;]+|$)", flags=re.UNICODE)
_PARENT = RelationshipRole.PARENT
_CHILD = RelationshipRole.CHILD
_SPOUSE = RelationshipRole.SPOUSE
_SIBLING = RelationshipRole.SIBLING


@dataclass(frozen=True)
class KinshipFrame:
    relationship_type: RelationshipType
    possessor_role: RelationshipRole
    relative_role: RelationshipRole


@dataclass(frozen=True)
class GroundingContext:
    text: str
    sentence_count: int


@dataclass(frozen=True)
class NameMatch:
    start: int
    end: int
    token: str
    grammatical_case: str | None = None
    suffix: str | None = None


def _frame(
    relationship_type: RelationshipType,
    possessor_role: RelationshipRole,
    relative_role: RelationshipRole,
) -> KinshipFrame:
    return KinshipFrame(relationship_type, possessor_role, relative_role)


_RU_FORMS: dict[str, KinshipFrame] = {
    **{
        value: _frame(RelationshipType.PARENT_CHILD, _CHILD, _PARENT)
        for value in (
            "отец",
            "отца",
            "отцом",
            "папа",
            "папы",
            "папой",
            "мать",
            "матери",
            "матерью",
            "мама",
            "мамы",
            "мамой",
        )
    },
    **{
        value: _frame(RelationshipType.PARENT_CHILD, _PARENT, _CHILD)
        for value in (
            "сын",
            "сына",
            "сыном",
            "сыновья",
            "сыновей",
            "дочь",
            "дочери",
            "дочерью",
            "дочерей",
            "ребенок",
            "ребёнок",
            "дети",
            "детей",
        )
    },
    **{
        value: _frame(RelationshipType.SIBLING, _SIBLING, _SIBLING)
        for value in (
            "брат",
            "брата",
            "братом",
            "сестра",
            "сестры",
            "сестрой",
            "сестрёнка",
            "сестренка",
        )
    },
    **{
        value: _frame(RelationshipType.SPOUSE, _SPOUSE, _SPOUSE)
        for value in ("муж", "мужа", "мужем", "жена", "жены", "женой")
    },
}
_KK_SPEAKER_FORMS: dict[str, KinshipFrame] = {
    value: _frame(RelationshipType.PARENT_CHILD, _PARENT, _CHILD)
    for value in (
        "балаларым",
        "балаларымыз",
        "ұлдарым",
        "ұлдарымыз",
        "қыздарым",
        "қыздарымыз",
    )
}
_KK_NAMED_FORMS: dict[str, KinshipFrame] = {
    value: _frame(RelationshipType.PARENT_CHILD, _PARENT, _CHILD)
    for value in ("балалары", "ұлдары", "қыздары")
}
_RU_FIRST_PERSON = frozenset(
    (
        "мой моя мое моё мои моего моей моему моем моём моим моими мою "
        "наш наша наше наши нашего нашей нашему нашем нашим нашими нашу"
    ).split()
)
_RU_COUSIN = frozenset("двоюродный двоюродная двоюродного двоюродной двоюродные".split())
_RELATION_LABELS = {
    "father": frozenset({"отец", "папа", "әке", "әкем"}),
    "mother": frozenset({"мать", "мама", "ана", "анам", "шеше", "шешем"}),
    "brother": frozenset({"брат", "аға", "ағам", "іні", "інім"}),
    "sister": frozenset({"сестра", "сестрёнка", "әпке", "әпкем", "сіңлі", "сіңлім"}),
    "husband": frozenset({"муж", "күйеу", "күйеуім"}),
    "wife": frozenset({"жена", "әйел", "әйелім"}),
    "son": frozenset({"сын", "ұл", "ұлым"}),
    "daughter": frozenset({"дочь", "қыз", "қызым"}),
}


def _surfaces(person: PersonMention) -> list[str]:
    values = [person.name, *person.aliases]
    values.extend(item.surface for item in person.name_variants)
    return list(dict.fromkeys(value for value in values if value))


def _is_speaker(person: PersonMention, speaker_name: str) -> bool:
    expected = normalize_text(speaker_name)
    return any(normalize_text(surface) == expected for surface in _surfaces(person))


def _name_matches(text: str, person: PersonMention) -> list[NameMatch]:
    matches: list[NameMatch] = []
    for surface in _surfaces(person):
        matches.extend(
            NameMatch(
                start=item.start,
                end=item.end,
                token=item.token,
                grammatical_case=item.grammatical_case,
            )
            for item in russian.find_known_name_matches(text, surface)
            if item.start >= 0
        )
        matches.extend(
            NameMatch(
                start=item.start,
                end=item.end,
                token=item.token,
                suffix=item.suffix,
            )
            for item in kazakh.find_known_name_matches(text, surface)
            if item.start >= 0
        )
    return list({(item.start, item.end, item.token): item for item in matches}.values())


def _split_units(text: str) -> list[str]:
    units = [match.group(0).strip() for match in _SENTENCE_RE.finditer(text)]
    result: list[str] = []
    for unit in (item for item in units if item):
        if len(unit) <= _MAX_CONTEXT_CHARS:
            result.append(unit)
            continue
        words = unit.split()
        current: list[str] = []
        for word in words:
            candidate = " ".join([*current, word])
            if current and len(candidate) > _MAX_CONTEXT_CHARS:
                result.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            result.append(" ".join(current))
    return result or ([text.strip()] if text.strip() else [])


def _windows(text: str) -> list[GroundingContext]:
    units = _split_units(text)
    values: dict[str, GroundingContext] = {}
    for start in range(len(units)):
        for count in range(1, _MAX_CONTEXT_SENTENCES + 1):
            selected = units[start : start + count]
            if len(selected) != count:
                break
            combined = " ".join(selected)
            if len(combined) > _MAX_CONTEXT_CHARS:
                break
            values.setdefault(normalize_text(combined), GroundingContext(combined, count))
    return list(values.values())


def _source_text(relationship: RelationshipClaim, transcript: TranscriptEnvelope) -> str:
    requested = set(relationship.source_segment_ids)
    return "\n".join(
        segment.text for segment in transcript.segments if segment.segment_id in requested
    )


def _label_supports(person: PersonMention, text: str) -> bool:
    label = normalize_text(person.relation_to_speaker or "")
    if not label:
        return False
    accepted = _RELATION_LABELS.get(label, frozenset({label}))
    return bool({item.normalized for item in tokenize(text)}.intersection(accepted))


def supported_endpoint_ids(
    *,
    contexts: list[GroundingContext],
    people: list[PersonMention],
    speaker_name: str,
    resolved_antecedent_ids: set[str],
) -> set[str]:
    supported: set[str] = set()
    for context in contexts:
        has_anchor = bool(find_speaker_anchor_matches(context.text))
        has_third_person = bool(find_third_person_possessive_markers(context.text))
        for person in people:
            if _name_matches(context.text, person):
                supported.add(person.mention_id)
            elif has_anchor and _is_speaker(person, speaker_name):
                supported.add(person.mention_id)
            elif _label_supports(person, context.text):
                supported.add(person.mention_id)
            elif has_third_person and person.mention_id in resolved_antecedent_ids:
                supported.add(person.mention_id)
    return supported


def select_relationship_grounding_contexts(
    *,
    relationship: RelationshipClaim,
    transcript: TranscriptEnvelope,
    people: list[PersonMention],
    speaker_name: str,
    resolved_antecedent_ids: set[str],
) -> list[GroundingContext]:
    mention_by_id = {person.mention_id: person for person in people}
    endpoint_ids = {relationship.subject_mention_id, relationship.object_mention_id}
    endpoints = [mention_by_id[item] for item in endpoint_ids if item in mention_by_id]
    if len(endpoints) != 2:
        return []
    eligible = []
    for window in _windows(_source_text(relationship, transcript)):
        supported = supported_endpoint_ids(
            contexts=[window],
            people=endpoints,
            speaker_name=speaker_name,
            resolved_antecedent_ids=set(),
        )
        if endpoint_ids.issubset(supported):
            eligible.append(window)
    eligible.sort(key=lambda item: (item.sentence_count, len(item.text), item.text))
    return eligible[:6]


def _is_negated(tokens: list[TextToken], index: int) -> bool:
    return any(item.normalized == "не" for item in tokens[max(0, index - 2) : index]) or any(
        item.normalized == "емес" for item in tokens[index + 1 : index + 3]
    )


def _is_cousin(tokens: list[TextToken], index: int) -> bool:
    return any(item.normalized in _RU_COUSIN for item in tokens[max(0, index - 2) : index])


def _masked(text: str) -> str:
    tokens = tokenize(text)
    result = list(text)
    for index, token in enumerate(tokens):
        frame = _RU_FORMS.get(token.normalized)
        is_kinship = frame is not None or token.normalized in _KK_SPEAKER_FORMS
        is_kinship = is_kinship or token.normalized in _KK_NAMED_FORMS
        cousin = frame is not None and frame.relationship_type is RelationshipType.SIBLING
        if not is_kinship or (
            not _is_negated(tokens, index) and not (cousin and _is_cousin(tokens, index))
        ):
            continue
        result[token.start : token.end] = " " * (token.end - token.start)
    return "".join(result)


def _canonical(
    *,
    language: str,
    possessor: PersonMention,
    relative: PersonMention,
    frame: KinshipFrame,
    surface: str,
    rule_id: str,
) -> LinguisticRelationshipSignal:
    if frame.relationship_type is RelationshipType.PARENT_CHILD:
        if frame.possessor_role is _PARENT:
            subject, subject_role, object_person, object_role = (
                possessor,
                _PARENT,
                relative,
                _CHILD,
            )
        else:
            subject, subject_role, object_person, object_role = (
                relative,
                _PARENT,
                possessor,
                _CHILD,
            )
    else:
        subject, subject_role, object_person, object_role = (
            possessor,
            frame.possessor_role,
            relative,
            frame.relative_role,
        )
    return LinguisticRelationshipSignal(
        language=language,
        relationship_type=frame.relationship_type,
        subject_mention_id=subject.mention_id,
        subject_role=subject_role,
        object_mention_id=object_person.mention_id,
        object_role=object_role,
        source_surface=surface,
        rule_id=rule_id,
    )


def _distance(start: int, end: int, matches: list[NameMatch]) -> int | None:
    values = [min(abs(item.start - end), abs(start - item.end)) for item in matches]
    return min(values) if values else None


def _speaker_signals(
    text: str,
    people: list[PersonMention],
    speaker_name: str,
) -> list[LinguisticRelationshipSignal]:
    speakers = [item for item in people if _is_speaker(item, speaker_name)]
    if len(speakers) != 1 or len(people) != 2:
        return []
    speaker = speakers[0]
    target = people[1] if people[0] is speaker else people[0]
    target_matches = _name_matches(text, target)
    tokens = tokenize(text)
    anchors = find_speaker_anchor_matches(text)
    result = []
    for index, token in enumerate(tokens):
        if _is_negated(tokens, index):
            continue
        frame = _RU_FORMS.get(token.normalized)
        language = "ru"
        if frame is None:
            frame = _KK_SPEAKER_FORMS.get(token.normalized)
            language = "kk"
        if frame is None:
            continue
        nearby_anchor = any(
            min(abs(item.start - token.end), abs(token.start - item.end)) <= 45 for item in anchors
        )
        ru_anchor = any(
            item.normalized in _RU_FIRST_PERSON for item in tokens[max(0, index - 4) : index]
        )
        if language == "ru" and not (nearby_anchor or ru_anchor):
            continue
        target_distance = _distance(token.start, token.end, target_matches)
        if target_distance is None or target_distance > 110:
            continue
        result.append(
            _canonical(
                language=language,
                possessor=speaker,
                relative=target,
                frame=frame,
                surface=token.surface,
                rule_id=(
                    "ru.relationship.speaker_inflected_kinship.v2"
                    if language == "ru"
                    else "kk.relationship.speaker_possessive_plural.v2"
                ),
            )
        )
    return result


def _u_frame(tokens: list[TextToken], possessor: NameMatch, kinship_index: int) -> bool:
    before = [
        (index, token)
        for index, token in enumerate(tokens)
        if token.end <= possessor.start and kinship_index - index <= 9
    ]
    return any(token.normalized == "у" for _, token in before[-5:])


def _dash_or_copula(text: str, left: int, right: int) -> bool:
    start, end = sorted((left, right))
    between = text[start:end]
    words = set(normalize_text(between).split())
    return "—" in between or "-" in between or bool(words.intersection({"это", "зовут"}))


def _named_signals(text: str, people: list[PersonMention]) -> list[LinguisticRelationshipSignal]:
    if len(people) != 2:
        return []
    tokens = tokenize(text)
    result = []
    for possessor in people:
        relative = people[1] if people[0] is possessor else people[0]
        possessor_matches = _name_matches(text, possessor)
        relative_matches = _name_matches(text, relative)
        for index, token in enumerate(tokens):
            if _is_negated(tokens, index):
                continue
            frame = _RU_FORMS.get(token.normalized)
            language = "ru"
            if frame is None:
                frame = _KK_NAMED_FORMS.get(token.normalized)
                language = "kk"
            if frame is None:
                continue
            for owner in possessor_matches:
                for target in relative_matches:
                    target_distance = _distance(token.start, token.end, [target])
                    if target_distance is None or target_distance > 160:
                        continue
                    if language == "kk":
                        genitive = owner.suffix in {
                            "ның",
                            "нің",
                            "дың",
                            "дің",
                            "тың",
                            "тің",
                        }
                        supported = genitive and owner.end <= token.start <= owner.end + 80
                    else:
                        in_u_frame = owner.end <= token.start and _u_frame(tokens, owner, index)
                        owner_after_kinship = token.end <= owner.start <= token.end + 90
                        target_outside = target.end <= token.start or target.start >= owner.end
                        genitive = owner.grammatical_case == "genitive"
                        supported = in_u_frame or (
                            owner_after_kinship
                            and target_outside
                            and (genitive or _dash_or_copula(text, owner.end, target.start))
                        )
                    if not supported:
                        continue
                    result.append(
                        _canonical(
                            language=language,
                            possessor=possessor,
                            relative=relative,
                            frame=frame,
                            surface=token.surface,
                            rule_id=f"{language}.relationship.named_possessor_local.v2",
                        )
                    )
    return result


def _explicit_pair_signals(
    text: str,
    people: list[PersonMention],
) -> list[LinguisticRelationshipSignal]:
    signals = [
        LinguisticRelationshipSignal(
            language=match.language,
            relationship_type=match.relationship_type,
            subject_mention_id=match.subject_mention_id,
            subject_role=_SPOUSE,
            object_mention_id=match.object_mention_id,
            object_role=_SPOUSE,
            source_surface=match.source_surface,
            rule_id=match.rule_id,
        )
        for match in find_explicit_pair_matches(text, people)
    ]
    signals.extend(find_explicit_sibling_signals(text, people))
    return signals


def find_bounded_relationship_signals(
    *,
    contexts: list[GroundingContext],
    people: list[PersonMention],
    speaker_name: str,
) -> list[LinguisticRelationshipSignal]:
    signals: list[LinguisticRelationshipSignal] = []
    for context in contexts:
        text = _masked(context.text)
        signals.extend(find_relationship_signals(text, people, speaker_name))
        signals.extend(_speaker_signals(text, people, speaker_name))
        signals.extend(_named_signals(text, people))
        for unit in _split_units(text):
            signals.extend(_explicit_pair_signals(unit, people))
    unique: dict[tuple[str, str, str, str, str], LinguisticRelationshipSignal] = {}
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


def grounding_rule_family(rule_id: str, relationship_type: RelationshipType) -> str:
    if "speaker" in rule_id:
        return "speaker_anchor"
    if "named" in rule_id:
        return "named_possessor"
    if relationship_type is RelationshipType.SPOUSE:
        return "explicit_spouse"
    if relationship_type is RelationshipType.PARENT_CHILD:
        return "explicit_parent_child"
    return "explicit_sibling"
