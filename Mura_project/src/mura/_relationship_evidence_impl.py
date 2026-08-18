from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mura.domain.models import (
    EvidenceClass,
    ExtractionResult,
    PersonMention,
    RelationshipClaim,
    TranscriptEnvelope,
)
from mura.linguistics.common import normalize_text
from mura.linguistics.multilingual import (
    LinguisticRelationshipSignal,
    contains_known_name_surface,
    find_known_name_matches,
    find_speaker_anchor_matches,
    find_third_person_possessive_markers,
    find_uncertainty_markers,
    signal_matches_relationship,
)
from mura.relationship_grounding import (
    find_bounded_relationship_signals,
    grounding_rule_family,
    select_relationship_grounding_contexts,
    supported_endpoint_ids,
)

_AUTO_ACCEPTABLE_CLASSES = {
    EvidenceClass.A_EXPLICIT,
    EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT,
    EvidenceClass.C_SPEAKER_ANCHORED,
}


def normalize_evidence(value: str) -> str:
    return normalize_text(value)


def contains_exact_surface(text: str, surface: str) -> bool:
    normalized_text = normalize_evidence(text)
    normalized_surface = normalize_evidence(surface)
    if not normalized_surface:
        return False
    return f" {normalized_surface} " in f" {normalized_text} "


def contains_surface(text: str, surface: str) -> bool:
    if contains_exact_surface(text, surface):
        return True
    return contains_known_name_surface(text, surface)


def person_name_surfaces(person: PersonMention) -> list[str]:
    values = [person.name, *person.aliases]
    values.extend(variant.surface for variant in person.name_variants)
    return list(dict.fromkeys(value for value in values if value))


def has_first_person_reference(text: str) -> bool:
    return bool(find_speaker_anchor_matches(text))


def joined_segment_text(
    segment_ids: list[str],
    transcript: TranscriptEnvelope,
) -> str:
    text_by_id = {segment.segment_id: segment.text for segment in transcript.segments}
    return " ".join(
        text_by_id[segment_id] for segment_id in segment_ids if segment_id in text_by_id
    )


def explicitly_named_people(
    source_text: str,
    people: list[PersonMention],
) -> list[PersonMention]:
    return [
        person
        for person in people
        if any(contains_surface(source_text, surface) for surface in person_name_surfaces(person))
    ]


def exactly_named_people(
    source_text: str,
    people: list[PersonMention],
) -> list[PersonMention]:
    return [
        person
        for person in people
        if any(
            contains_exact_surface(source_text, surface) for surface in person_name_surfaces(person)
        )
    ]


def speaker_mentions(
    people: list[PersonMention],
    speaker_name: str,
) -> list[PersonMention]:
    normalized_speaker = normalize_evidence(speaker_name)
    return [
        person
        for person in people
        if any(
            normalize_evidence(surface) == normalized_speaker
            for surface in person_name_surfaces(person)
        )
    ]


@dataclass(frozen=True)
class RelationshipEvidenceAnalysis:
    relationship_id: str
    source_segment_ids: list[str]
    source_text: str
    grounding_context_count: int
    subject_mention_id: str
    subject_name: str | None
    object_mention_id: str
    object_name: str | None
    explicit_people: list[dict[str, str]]
    exact_people: list[dict[str, str]]
    morphological_people: list[dict[str, str]]
    speaker_mention_ids: list[str]
    first_person_reference: bool
    speaker_anchor_matches: list[dict[str, Any]]
    supported_endpoint_ids: list[str]
    unsupported_endpoint_ids: list[str]
    evidence_class: str
    auto_accept_eligible: bool
    coreference_link_ids: list[str]
    resolved_coreference_antecedent_ids: list[str]
    linguistic_relationship_signals: list[dict[str, str]]
    matching_signal_rule_ids: list[str]
    conflicting_signal_rule_ids: list[str]
    kazakh_relationship_signals: list[dict[str, str]]
    russian_relationship_signals: list[dict[str, str]]
    english_relationship_signals: list[dict[str, str]]
    code_switching_relationship_signals: list[dict[str, str]]
    role_consistent: bool | None
    grounding_decision: str
    third_person_possessive_markers: list[dict[str, Any]]
    uncertainty_markers: list[dict[str, Any]]
    linguistic_rule_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _name_rule_ids(
    source_text: str,
    people: list[PersonMention],
) -> list[str]:
    rule_ids = {
        match.rule_id
        for person in people
        for surface in person_name_surfaces(person)
        for match in find_known_name_matches(source_text, surface)
    }
    return sorted(rule_ids)


def _signal_specificity(
    signal: LinguisticRelationshipSignal,
) -> tuple[int, int]:
    normalized = normalize_evidence(signal.source_surface)
    tokens = normalized.split()
    return len(tokens), len(normalized)


def _prefer_specific_endpoint_signals(
    signals: list[LinguisticRelationshipSignal],
) -> list[LinguisticRelationshipSignal]:
    grouped: dict[
        tuple[str, str, frozenset[str]],
        list[LinguisticRelationshipSignal],
    ] = {}
    for signal in signals:
        key = (
            signal.language,
            signal.relationship_type.value,
            frozenset(
                {
                    signal.subject_mention_id,
                    signal.object_mention_id,
                }
            ),
        )
        grouped.setdefault(key, []).append(signal)

    selected: list[LinguisticRelationshipSignal] = []
    for candidates in grouped.values():
        strongest = max(_signal_specificity(candidate) for candidate in candidates)
        selected.extend(
            candidate for candidate in candidates if _signal_specificity(candidate) == strongest
        )
    return selected


def _decision(
    *,
    matching_signals: list[LinguisticRelationshipSignal],
    conflicting_signals: list[LinguisticRelationshipSignal],
    unsupported: list[str],
    coreference_authorized: bool,
) -> str:
    if conflicting_signals:
        return "conflicting_deterministic_signal"
    if matching_signals:
        return grounding_rule_family(
            matching_signals[0].rule_id,
            matching_signals[0].relationship_type,
        )
    if coreference_authorized:
        return "resolved_coreference"
    if unsupported:
        return "unsupported_endpoints"
    return "insufficient_deterministic_signal"


def analyze_relationship_evidence(
    *,
    relationship: RelationshipClaim,
    transcript: TranscriptEnvelope,
    people: list[PersonMention],
    speaker_name: str,
    resolved_coreference_antecedent_ids: set[str] | None = None,
) -> RelationshipEvidenceAnalysis:
    resolved_antecedents = resolved_coreference_antecedent_ids or set()
    mention_by_id = {person.mention_id: person for person in people}
    endpoint_ids = [
        relationship.subject_mention_id,
        relationship.object_mention_id,
    ]
    endpoint_set = set(endpoint_ids)
    endpoint_people = [mention_by_id[item] for item in endpoint_ids if item in mention_by_id]

    contexts = select_relationship_grounding_contexts(
        relationship=relationship,
        transcript=transcript,
        people=people,
        speaker_name=speaker_name,
        resolved_antecedent_ids=resolved_antecedents,
    )
    source_text = " ".join(context.text for context in contexts)
    explicit = explicitly_named_people(source_text, people)
    exact = exactly_named_people(source_text, people)
    exact_ids = {person.mention_id for person in exact}
    morphological = [person for person in explicit if person.mention_id not in exact_ids]
    speakers = speaker_mentions(people, speaker_name)
    speaker_ids = {person.mention_id for person in speakers}
    speaker_anchors = find_speaker_anchor_matches(source_text)
    first_person = bool(speaker_anchors)

    signals = _prefer_specific_endpoint_signals(
        find_bounded_relationship_signals(
            contexts=contexts,
            people=endpoint_people,
            speaker_name=speaker_name,
        )
    )
    endpoint_signals = [
        signal
        for signal in signals
        if {
            signal.subject_mention_id,
            signal.object_mention_id,
        }
        == endpoint_set
    ]
    matching_signals = [
        signal for signal in endpoint_signals if signal_matches_relationship(signal, relationship)
    ]
    conflicting_signals = [
        signal
        for signal in endpoint_signals
        if not signal_matches_relationship(signal, relationship)
    ]
    third_person_markers = find_third_person_possessive_markers(source_text)
    resolved_endpoint_antecedents = endpoint_set.intersection(resolved_antecedents)
    coreference_authorized = bool(third_person_markers and resolved_endpoint_antecedents)
    unresolved_third_person = bool(third_person_markers) and not coreference_authorized

    if unresolved_third_person or conflicting_signals:
        role_consistent: bool | None = False
    elif matching_signals:
        role_consistent = True
    elif coreference_authorized:
        role_consistent = None
    else:
        role_consistent = False

    context_supported = supported_endpoint_ids(
        contexts=contexts,
        people=endpoint_people,
        speaker_name=speaker_name,
        resolved_antecedent_ids=resolved_antecedents,
    )
    supported = [mention_id for mention_id in endpoint_ids if mention_id in context_supported]
    unsupported = [mention_id for mention_id in endpoint_ids if mention_id not in context_supported]

    if coreference_authorized:
        evidence_class = EvidenceClass.D_CONTEXT_RESOLVED
    elif not unsupported and first_person and endpoint_set.intersection(speaker_ids):
        evidence_class = EvidenceClass.C_SPEAKER_ANCHORED
    elif endpoint_set.issubset(exact_ids):
        evidence_class = EvidenceClass.A_EXPLICIT
    elif not unsupported:
        evidence_class = EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT
    elif relationship.assertion_mode.value == "inferred":
        evidence_class = EvidenceClass.E_INFERRED
    else:
        evidence_class = EvidenceClass.U_UNCERTAIN

    uncertainty_markers = find_uncertainty_markers(source_text)
    rule_ids = set(_name_rule_ids(source_text, people))
    rule_ids.update(anchor.rule_id for anchor in speaker_anchors)
    rule_ids.update(signal.rule_id for signal in signals)
    rule_ids.update(marker.rule_id for marker in third_person_markers)
    rule_ids.update(marker.rule_id for marker in uncertainty_markers)
    signal_dicts = [signal.to_dict() for signal in signals]
    subject = mention_by_id.get(relationship.subject_mention_id)
    object_person = mention_by_id.get(relationship.object_mention_id)
    grounding_decision = _decision(
        matching_signals=matching_signals,
        conflicting_signals=conflicting_signals,
        unsupported=unsupported,
        coreference_authorized=coreference_authorized,
    )

    return RelationshipEvidenceAnalysis(
        relationship_id=relationship.relationship_id,
        source_segment_ids=list(relationship.source_segment_ids),
        source_text=source_text,
        grounding_context_count=len(contexts),
        subject_mention_id=relationship.subject_mention_id,
        subject_name=subject.name if subject else None,
        object_mention_id=relationship.object_mention_id,
        object_name=(object_person.name if object_person else None),
        explicit_people=[
            {
                "mention_id": person.mention_id,
                "name": person.name,
            }
            for person in explicit
        ],
        exact_people=[
            {
                "mention_id": person.mention_id,
                "name": person.name,
            }
            for person in exact
        ],
        morphological_people=[
            {
                "mention_id": person.mention_id,
                "name": person.name,
            }
            for person in morphological
        ],
        speaker_mention_ids=sorted(speaker_ids),
        first_person_reference=first_person,
        speaker_anchor_matches=[anchor.to_dict() for anchor in speaker_anchors],
        supported_endpoint_ids=supported,
        unsupported_endpoint_ids=unsupported,
        evidence_class=evidence_class.value,
        auto_accept_eligible=(
            evidence_class in _AUTO_ACCEPTABLE_CLASSES and role_consistent is True
        ),
        coreference_link_ids=list(relationship.coreference_link_ids),
        resolved_coreference_antecedent_ids=sorted(resolved_antecedents),
        linguistic_relationship_signals=signal_dicts,
        matching_signal_rule_ids=sorted({item.rule_id for item in matching_signals}),
        conflicting_signal_rule_ids=sorted({item.rule_id for item in conflicting_signals}),
        kazakh_relationship_signals=[item for item in signal_dicts if item["language"] == "kk"],
        russian_relationship_signals=[item for item in signal_dicts if item["language"] == "ru"],
        english_relationship_signals=[item for item in signal_dicts if item["language"] == "en"],
        code_switching_relationship_signals=[
            item for item in signal_dicts if item["language"] == "mixed"
        ],
        role_consistent=role_consistent,
        grounding_decision=grounding_decision,
        third_person_possessive_markers=[marker.to_dict() for marker in third_person_markers],
        uncertainty_markers=[marker.to_dict() for marker in uncertainty_markers],
        linguistic_rule_ids=sorted(rule_ids),
    )


def relationship_grounding_metrics(
    result: ExtractionResult,
    transcript: TranscriptEnvelope,
) -> dict[str, int]:
    counters = {
        "speaker_anchor_accepted": 0,
        "named_possessor_accepted": 0,
        "explicit_spouse_accepted": 0,
        "explicit_parent_child_accepted": 0,
        "explicit_sibling_accepted": 0,
    }
    for relationship in result.relationship_claims:
        analysis = analyze_relationship_evidence(
            relationship=relationship,
            transcript=transcript,
            people=result.people_mentions,
            speaker_name=result.speaker_name,
        )
        key = f"{analysis.grounding_decision}_accepted"
        if key in counters:
            counters[key] += 1
    return counters
