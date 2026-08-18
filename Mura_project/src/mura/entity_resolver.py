from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from mura.claim_semantics import relationship_is_active_candidate
from mura.domain.models import (
    AssertionMode,
    EpistemicStatus,
    EvidenceClass,
    ExtractionResult,
    KnownPerson,
    MentionResolution,
    NameVariantType,
    PersonMention,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    ResolutionStatus,
)
from mura.entity_resolution import (
    EntityResolutionContext,
    EntityResolutionMetrics,
    EntityResolutionRun,
    KnownPersonProfile,
    ResolutionSignal,
    ResolutionSignalKind,
    ResolutionTrace,
    categories_conflict,
    legacy_resolution_context,
)


@dataclass
class _CandidateState:
    profile: KnownPersonProfile
    supporting: list[ResolutionSignal] = field(default_factory=list)
    conflicting: list[ResolutionSignal] = field(default_factory=list)

    @property
    def person_id(self) -> str:
        return self.profile.person.person_id

    def has_support(self, kind: ResolutionSignalKind) -> bool:
        return any(signal.kind is kind for signal in self.supporting)


_RELATION_GENERATIONS = {
    "self": 0,
    "spouse": 0,
    "husband": 0,
    "wife": 0,
    "sibling": 0,
    "brother": 0,
    "sister": 0,
    "older brother": 0,
    "younger brother": 0,
    "older sister": 0,
    "younger sister": 0,
    "parent": -1,
    "father": -1,
    "mother": -1,
    "child": 1,
    "son": 1,
    "daughter": 1,
    "grandparent": -2,
    "grandfather": -2,
    "grandmother": -2,
    "grandchild": 2,
    "grandson": 2,
    "granddaughter": 2,
    "әке": -1,
    "әкесі": -1,
    "ана": -1,
    "анасы": -1,
    "шеше": -1,
    "шешесі": -1,
    "ұл": 1,
    "ұлы": 1,
    "қыз": 1,
    "қызы": 1,
    "бала": 1,
    "баласы": 1,
    "аға": 0,
    "іні": 0,
    "әпке": 0,
    "сіңлі": 0,
    "қарындас": 0,
    "отец": -1,
    "мать": -1,
    "сын": 1,
    "дочь": 1,
    "брат": 0,
    "сестра": 0,
}

_STRONG_ALIAS_VARIANTS = {
    NameVariantType.EXPLICIT_ALIAS,
    NameVariantType.NICKNAME,
    NameVariantType.DIMINUTIVE,
    NameVariantType.TRANSLITERATION,
    NameVariantType.SCRIPT_VARIANT,
    NameVariantType.ASR_VARIANT,
}
_GRAPH_ELIGIBLE_EVIDENCE_CLASSES = {
    EvidenceClass.A_EXPLICIT,
    EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT,
    EvidenceClass.C_SPEAKER_ANCHORED,
}


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)


def _normalize_relation(value: str | None) -> str | None:
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.replace("_", " ").split()) or None


def _mention_generation(mention: PersonMention) -> int | None:
    relation = _normalize_relation(mention.relation_to_speaker)
    return _RELATION_GENERATIONS.get(relation) if relation is not None else None


def _unique_signals(signals: list[ResolutionSignal]) -> list[ResolutionSignal]:
    unique: dict[tuple[str, str, str | None, str | None, str | None], ResolutionSignal] = {}
    for signal in signals:
        key = (
            signal.rule_id,
            signal.detail,
            signal.person_id,
            signal.related_mention_id,
            signal.related_person_id,
        )
        unique.setdefault(key, signal)
    return list(unique.values())


def _candidate_name_signals(
    mention: PersonMention,
    profile: KnownPersonProfile,
) -> list[ResolutionSignal]:
    person = profile.person
    canonical = normalize_name(person.canonical_name)
    aliases = {normalize_name(alias) for alias in person.aliases if normalize_name(alias)}
    verified_aliases = {
        normalize_name(alias) for alias in profile.verified_aliases if normalize_name(alias)
    }
    signals: list[ResolutionSignal] = []

    normalized_primary = normalize_name(mention.name)
    if normalized_primary and normalized_primary == canonical:
        signals.append(
            ResolutionSignal(
                rule_id="resolution.name.canonical_exact.v3",
                kind=ResolutionSignalKind.CANONICAL_NAME,
                detail="mention primary name matches the archive canonical name",
                person_id=person.person_id,
            )
        )
    if normalized_primary and normalized_primary in aliases:
        signals.append(
            ResolutionSignal(
                rule_id="resolution.name.archive_alias_candidate.v3",
                kind=ResolutionSignalKind.ARCHIVE_ALIAS,
                detail="mention primary name matches an archive alias candidate",
                person_id=person.person_id,
            )
        )
    if normalized_primary and normalized_primary in verified_aliases:
        signals.append(
            ResolutionSignal(
                rule_id="resolution.name.verified_alias.v3",
                kind=ResolutionSignalKind.ESTABLISHED_ALIAS,
                detail="mention primary name matches a human-verified archive alias",
                person_id=person.person_id,
            )
        )

    # Plain model aliases can nominate candidates, but never authorize an auto-merge.
    for alias in mention.aliases:
        normalized = normalize_name(alias)
        if not normalized:
            continue
        if normalized == canonical or normalized in aliases:
            signals.append(
                ResolutionSignal(
                    rule_id="resolution.name.mention_alias_candidate.v1",
                    kind=ResolutionSignalKind.ARCHIVE_ALIAS,
                    detail="evidence-backed mention alias overlaps an archive name surface",
                    person_id=person.person_id,
                )
            )

    for variant in mention.name_variants:
        if variant.variant_type not in _STRONG_ALIAS_VARIANTS or not variant.evidence_ids:
            continue
        normalized = normalize_name(variant.surface)
        if not normalized:
            continue
        if normalized == canonical:
            signals.append(
                ResolutionSignal(
                    rule_id="resolution.name.structured_canonical_variant.v3",
                    kind=ResolutionSignalKind.STRUCTURED_ALIAS,
                    detail=(
                        "an evidence-backed transliteration, script, ASR, nickname, or "
                        "diminutive variant matches the canonical archive name"
                    ),
                    person_id=person.person_id,
                )
            )
        elif normalized in verified_aliases:
            signals.append(
                ResolutionSignal(
                    rule_id="resolution.name.structured_verified_alias.v3",
                    kind=ResolutionSignalKind.ESTABLISHED_ALIAS,
                    detail="an evidence-backed structured variant matches a verified alias",
                    person_id=person.person_id,
                )
            )
        elif normalized in aliases:
            signals.append(
                ResolutionSignal(
                    rule_id="resolution.name.structured_unverified_alias.v3",
                    kind=ResolutionSignalKind.ARCHIVE_ALIAS,
                    detail="a structured variant matches an unverified archive alias candidate",
                    person_id=person.person_id,
                )
            )
    return _unique_signals(signals)


def _candidate_state(mention: PersonMention, profile: KnownPersonProfile) -> _CandidateState | None:
    name_signals = _candidate_name_signals(mention, profile)
    if not name_signals:
        return None

    state = _CandidateState(profile=profile, supporting=name_signals)
    state.supporting.append(
        ResolutionSignal(
            rule_id="resolution.scope.same_family.v1",
            kind=ResolutionSignalKind.FAMILY_SCOPE,
            detail=f"candidate belongs to family archive {profile.family_id}",
            person_id=profile.person.person_id,
        )
    )

    uncertainty_status = mention.uncertainty.status if mention.uncertainty is not None else None
    if mention.assertion_mode is AssertionMode.UNCERTAIN or uncertainty_status in {
        EpistemicStatus.UNCERTAIN,
        EpistemicStatus.REMEMBERED_IMPRECISELY,
        EpistemicStatus.REPORTED,
        EpistemicStatus.COMPETING,
        EpistemicStatus.UNRESOLVED,
    }:
        state.conflicting.append(
            ResolutionSignal(
                rule_id="resolution.guard.uncertain_mention.v1",
                kind=ResolutionSignalKind.UNCERTAIN_MENTION,
                detail="uncertain or reported identity mention requires human review",
                person_id=profile.person.person_id,
            )
        )

    mention_relation = _normalize_relation(mention.relation_to_speaker)
    known_relation = _normalize_relation(profile.person.relation_to_speaker)
    if mention_relation and known_relation:
        if mention_relation == known_relation:
            state.supporting.append(
                ResolutionSignal(
                    rule_id="resolution.context.relation_match.v2",
                    kind=ResolutionSignalKind.RELATION_TO_SPEAKER,
                    detail=f"relation_to_speaker agrees as {mention_relation!r}",
                    person_id=profile.person.person_id,
                )
            )
        else:
            state.conflicting.append(
                ResolutionSignal(
                    rule_id="resolution.guard.relation_conflict.v2",
                    kind=ResolutionSignalKind.RELATION_CONFLICT,
                    detail=(
                        f"mention relation {mention_relation!r} conflicts with archive relation "
                        f"{known_relation!r}"
                    ),
                    person_id=profile.person.person_id,
                )
            )

    mention_generation = _mention_generation(mention)
    profile_generation = profile.generation_relative_to_speaker
    if mention_generation is not None and profile_generation is not None:
        if mention_generation == profile_generation:
            state.supporting.append(
                ResolutionSignal(
                    rule_id="resolution.context.generation_match.v1",
                    kind=ResolutionSignalKind.GENERATION,
                    detail=f"speaker-relative generation agrees at {mention_generation}",
                    person_id=profile.person.person_id,
                )
            )
        else:
            state.conflicting.append(
                ResolutionSignal(
                    rule_id="resolution.guard.generation_conflict.v1",
                    kind=ResolutionSignalKind.GENERATION_CONFLICT,
                    detail=(
                        "mention generation "
                        f"{mention_generation} conflicts with speaker-relative archive generation "
                        f"{profile_generation}"
                    ),
                    person_id=profile.person.person_id,
                )
            )

    if categories_conflict(mention.category, profile.person.category):
        state.conflicting.append(
            ResolutionSignal(
                rule_id="resolution.guard.category_conflict.v1",
                kind=ResolutionSignalKind.CATEGORY_CONFLICT,
                detail=(
                    f"mention category {mention.category.value} conflicts with archive category "
                    f"{profile.person.category.value}"
                ),
                person_id=profile.person.person_id,
            )
        )
    elif (
        mention.category.value != "unknown"
        and profile.person.category.value != "unknown"
        and mention.category is profile.person.category
    ):
        state.supporting.append(
            ResolutionSignal(
                rule_id="resolution.context.category_match.v1",
                kind=ResolutionSignalKind.CATEGORY,
                detail=f"person category agrees as {mention.category.value}",
                person_id=profile.person.person_id,
            )
        )
    return state


def _is_seed_resolvable(state: _CandidateState) -> bool:
    if state.conflicting:
        return False
    if state.has_support(ResolutionSignalKind.ESTABLISHED_ALIAS):
        return True
    if state.has_support(ResolutionSignalKind.STRUCTURED_ALIAS):
        return True
    return state.has_support(ResolutionSignalKind.RELATION_TO_SPEAKER) and state.has_support(
        ResolutionSignalKind.GENERATION
    )


def _neighbour_id_for(
    relationship: RelationshipClaim,
    mention_id: str,
) -> tuple[str, RelationshipRole, RelationshipRole] | None:
    if relationship.subject_mention_id == mention_id:
        return (
            relationship.object_mention_id,
            relationship.subject_role,
            relationship.object_role,
        )
    if relationship.object_mention_id == mention_id:
        return (
            relationship.subject_mention_id,
            relationship.object_role,
            relationship.subject_role,
        )
    return None


def _expected_neighbour_ids(
    profile: KnownPersonProfile,
    relationship_type: RelationshipType,
    mention_role: RelationshipRole,
) -> set[str]:
    if relationship_type is RelationshipType.SPOUSE:
        return set(profile.spouse_person_ids)
    if relationship_type is RelationshipType.SIBLING:
        return set(profile.sibling_person_ids)
    if relationship_type is RelationshipType.PARENT_CHILD:
        if mention_role is RelationshipRole.PARENT:
            return set(profile.child_person_ids)
        if mention_role is RelationshipRole.CHILD:
            return set(profile.parent_person_ids)
    return set()


def _add_graph_signals(
    *,
    extraction: ExtractionResult,
    mention_id: str,
    state: _CandidateState,
    seed_person_by_mention: dict[str, str],
) -> None:
    for relationship in extraction.relationship_claims:
        if not relationship_is_active_candidate(relationship):
            continue
        if (
            relationship.evidence_class not in _GRAPH_ELIGIBLE_EVIDENCE_CLASSES
            or not relationship.evidence_ids
        ):
            continue
        neighbour = _neighbour_id_for(relationship, mention_id)
        if neighbour is None:
            continue
        neighbour_mention_id, mention_role, _ = neighbour
        neighbour_person_id = seed_person_by_mention.get(neighbour_mention_id)
        if neighbour_person_id is None:
            continue
        expected = _expected_neighbour_ids(
            state.profile,
            relationship.relationship_type,
            mention_role,
        )
        if neighbour_person_id not in expected:
            continue
        state.supporting.append(
            ResolutionSignal(
                rule_id="resolution.context.graph_neighbour_match.v1",
                kind=ResolutionSignalKind.GRAPH_NEIGHBOUR,
                detail=(
                    f"grounded {relationship.relationship_type.value} claim agrees with archive "
                    f"neighbour {neighbour_person_id}"
                ),
                person_id=state.person_id,
                related_mention_id=neighbour_mention_id,
                related_person_id=neighbour_person_id,
            )
        )


def _is_final_resolvable(state: _CandidateState) -> bool:
    if state.conflicting:
        return False
    if _is_seed_resolvable(state):
        return True
    return state.has_support(ResolutionSignalKind.GRAPH_NEIGHBOUR)


def _trace_to_resolution(trace: ResolutionTrace) -> MentionResolution:
    return MentionResolution(
        mention_id=trace.mention_id,
        status=trace.status,
        person_id=trace.selected_person_id,
        candidate_person_ids=trace.candidate_person_ids,
        reason=trace.reason,
    )


def _verified_alias_collision(states: list[_CandidateState]) -> bool:
    return sum(state.has_support(ResolutionSignalKind.ESTABLISHED_ALIAS) for state in states) > 1


def _incompatible_mention_pairs(extraction: ExtractionResult) -> set[frozenset[str]]:
    return {
        frozenset((relationship.subject_mention_id, relationship.object_mention_id))
        for relationship in extraction.relationship_claims
        if relationship_is_active_candidate(relationship)
        and relationship.evidence_class in _GRAPH_ELIGIBLE_EVIDENCE_CLASSES
        and relationship.evidence_ids
    }


def _identity_collision_pairs(
    selected: dict[str, _CandidateState],
    incompatible_pairs: set[frozenset[str]],
) -> set[frozenset[str]]:
    collisions: set[frozenset[str]] = set()
    for pair in incompatible_pairs:
        mention_ids = sorted(pair)
        if len(mention_ids) != 2:
            continue
        first = selected.get(mention_ids[0])
        second = selected.get(mention_ids[1])
        if first is not None and second is not None and first.person_id == second.person_id:
            collisions.add(pair)
    return collisions


def _add_collision_signal(
    states: list[_CandidateState],
    *,
    rule_id: str,
    kind: ResolutionSignalKind,
    detail: str,
) -> None:
    for state in states:
        state.conflicting.append(
            ResolutionSignal(
                rule_id=rule_id,
                kind=kind,
                detail=detail,
                person_id=state.person_id,
            )
        )
        state.conflicting = _unique_signals(state.conflicting)


def resolve_mentions_with_report(
    extraction: ExtractionResult,
    context: EntityResolutionContext,
) -> EntityResolutionRun:
    states_by_mention: dict[str, list[_CandidateState]] = {}
    verified_alias_collision_mentions: set[str] = set()
    for mention in extraction.people_mentions:
        states = [
            state
            for profile in context.profiles
            if (state := _candidate_state(mention, profile)) is not None
        ]
        states = sorted(states, key=lambda item: item.person_id)
        states_by_mention[mention.mention_id] = states
        if _verified_alias_collision(states):
            verified_alias_collision_mentions.add(mention.mention_id)
            _add_collision_signal(
                states,
                rule_id="resolution.guard.verified_alias_collision.v1",
                kind=ResolutionSignalKind.VERIFIED_ALIAS_COLLISION,
                detail="the same mention surface is a verified alias for multiple people",
            )

    incompatible_pairs = _incompatible_mention_pairs(extraction)
    seed_state_by_mention: dict[str, _CandidateState] = {}
    for mention_id, states in states_by_mention.items():
        compatible = [state for state in states if not state.conflicting]
        if (
            mention_id not in verified_alias_collision_mentions
            and len(compatible) == 1
            and _is_seed_resolvable(compatible[0])
        ):
            seed_state_by_mention[mention_id] = compatible[0]

    seed_collisions = _identity_collision_pairs(seed_state_by_mention, incompatible_pairs)
    collision_mentions = {mention_id for pair in seed_collisions for mention_id in pair}
    for mention_id in collision_mentions:
        seed_state_by_mention.pop(mention_id, None)
        _add_collision_signal(
            states_by_mention[mention_id],
            rule_id="resolution.guard.relationship_endpoint_collision.v1",
            kind=ResolutionSignalKind.MENTION_COLLISION,
            detail="distinct relationship endpoints cannot resolve to the same archive person",
        )

    seed_person_by_mention = {
        mention_id: state.person_id for mention_id, state in seed_state_by_mention.items()
    }
    for mention_id, states in states_by_mention.items():
        for state in states:
            _add_graph_signals(
                extraction=extraction,
                mention_id=mention_id,
                state=state,
                seed_person_by_mention=seed_person_by_mention,
            )
            state.supporting = _unique_signals(state.supporting)
            state.conflicting = _unique_signals(state.conflicting)

    selected_by_mention: dict[str, _CandidateState] = {}
    for mention in extraction.people_mentions:
        states = states_by_mention[mention.mention_id]
        compatible = [state for state in states if not state.conflicting]
        resolvable = [state for state in compatible if _is_final_resolvable(state)]
        if (
            mention.mention_id not in verified_alias_collision_mentions
            and len(resolvable) == 1
            and len(compatible) == 1
        ):
            selected_by_mention[mention.mention_id] = resolvable[0]

    final_collisions = _identity_collision_pairs(selected_by_mention, incompatible_pairs)
    all_collisions = seed_collisions | final_collisions
    final_collision_mentions = {mention_id for pair in final_collisions for mention_id in pair}
    for mention_id in final_collision_mentions:
        selected_by_mention.pop(mention_id, None)
        _add_collision_signal(
            states_by_mention[mention_id],
            rule_id="resolution.guard.relationship_endpoint_collision.v1",
            kind=ResolutionSignalKind.MENTION_COLLISION,
            detail="distinct relationship endpoints cannot resolve to the same archive person",
        )

    traces: list[ResolutionTrace] = []
    for mention in extraction.people_mentions:
        states = states_by_mention[mention.mention_id]
        candidate_ids = [state.person_id for state in states]
        selected = selected_by_mention.get(mention.mention_id)

        if selected is not None:
            rule_ids = list(dict.fromkeys(signal.rule_id for signal in selected.supporting))
            traces.append(
                ResolutionTrace(
                    mention_id=mention.mention_id,
                    status=ResolutionStatus.RESOLVED,
                    selected_person_id=selected.person_id,
                    candidate_person_ids=candidate_ids,
                    supporting_signals=selected.supporting,
                    conflicting_signals=selected.conflicting,
                    rule_ids=rule_ids,
                    reason=(
                        "one archive candidate has deterministic identity support beyond name "
                        "equality and no conflicting family or mention context"
                    ),
                )
            )
            continue

        if states:
            all_support = _unique_signals(
                [signal for state in states for signal in state.supporting]
            )
            all_conflicts = _unique_signals(
                [signal for state in states for signal in state.conflicting]
            )
            traces.append(
                ResolutionTrace(
                    mention_id=mention.mention_id,
                    status=ResolutionStatus.NEEDS_REVIEW,
                    candidate_person_ids=candidate_ids,
                    supporting_signals=all_support,
                    conflicting_signals=all_conflicts,
                    rule_ids=list(
                        dict.fromkeys(signal.rule_id for signal in [*all_support, *all_conflicts])
                    ),
                    reason=(
                        "name overlap exists, but identity is ambiguous, insufficiently "
                        "corroborated, or contradicted by archive or mention context"
                    ),
                )
            )
            continue

        traces.append(
            ResolutionTrace(
                mention_id=mention.mention_id,
                status=ResolutionStatus.NEW_PERSON,
                candidate_person_ids=[],
                rule_ids=["resolution.decision.no_in_scope_name_candidate.v3"],
                reason=(
                    "no same-family canonical-name, archive-alias, or structured-variant candidate"
                ),
            )
        )

    resolutions = [_trace_to_resolution(trace) for trace in traces]
    inactive_relationships_ignored = sum(
        not relationship_is_active_candidate(relationship)
        for relationship in extraction.relationship_claims
    )
    return EntityResolutionRun(
        family_id=context.family_id,
        resolutions=resolutions,
        traces=traces,
        metrics=EntityResolutionMetrics(
            mentions=len(traces),
            resolved=sum(trace.status is ResolutionStatus.RESOLVED for trace in traces),
            needs_review=sum(trace.status is ResolutionStatus.NEEDS_REVIEW for trace in traces),
            new_person=sum(trace.status is ResolutionStatus.NEW_PERSON for trace in traces),
            family_scope_violations=0,
            verified_alias_collisions=len(verified_alias_collision_mentions),
            mention_identity_collisions=len(all_collisions),
            inactive_relationships_ignored=inactive_relationships_ignored,
        ),
    )


def resolve_mentions(
    extraction: ExtractionResult,
    known_people: list[KnownPerson] | None = None,
    *,
    context: EntityResolutionContext | None = None,
) -> list[MentionResolution]:
    resolved_context = context or legacy_resolution_context(known_people or [])
    return resolve_mentions_with_report(extraction, resolved_context).resolutions
