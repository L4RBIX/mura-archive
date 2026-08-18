from __future__ import annotations

import hashlib
import re

from mura.coreference_context import BoundedCoreferenceContext
from mura.coreference_language import KinshipFrame
from mura.coreference_units import TextUnit
from mura.domain.models import (
    CoreferenceMethod,
    CoreferenceStatus,
    EvidenceClass,
    EvidencePurpose,
    EvidenceSpan,
    ExtractionResult,
    GrammaticalNumber,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    TranscriptEnvelope,
)

_TRUSTED_RESOLVED_METHODS = {
    CoreferenceMethod.DETERMINISTIC_DISCOURSE,
    CoreferenceMethod.HUMAN_REVIEW,
}


def safe_id(value: str) -> str:
    normalized = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE).strip("_")
    return normalized or "unknown"


def ordered_segment_ids(
    segment_ids: list[str],
    transcript: TranscriptEnvelope,
) -> list[str]:
    requested = set(segment_ids)
    ordered = [
        segment.segment_id for segment in transcript.segments if segment.segment_id in requested
    ]
    seen = set(ordered)
    ordered.extend(item for item in segment_ids if item not in seen)
    return list(dict.fromkeys(ordered))


def _expected_edge(
    possessor_id: str,
    target_id: str,
    frame: KinshipFrame,
) -> tuple[RelationshipType, str, RelationshipRole, str, RelationshipRole]:
    if frame.relationship_type is RelationshipType.PARENT_CHILD:
        if frame.possessor_role is RelationshipRole.PARENT:
            return (
                frame.relationship_type,
                possessor_id,
                RelationshipRole.PARENT,
                target_id,
                RelationshipRole.CHILD,
            )
        return (
            frame.relationship_type,
            target_id,
            RelationshipRole.PARENT,
            possessor_id,
            RelationshipRole.CHILD,
        )
    if frame.relationship_type is RelationshipType.SIBLING:
        if frame.possessor_role is RelationshipRole.OLDER_SIBLING:
            return (
                frame.relationship_type,
                possessor_id,
                RelationshipRole.OLDER_SIBLING,
                target_id,
                RelationshipRole.YOUNGER_SIBLING,
            )
        if frame.relative_role is RelationshipRole.OLDER_SIBLING:
            return (
                frame.relationship_type,
                target_id,
                RelationshipRole.OLDER_SIBLING,
                possessor_id,
                RelationshipRole.YOUNGER_SIBLING,
            )
        return (
            frame.relationship_type,
            possessor_id,
            RelationshipRole.SIBLING,
            target_id,
            RelationshipRole.SIBLING,
        )
    return (
        frame.relationship_type,
        possessor_id,
        RelationshipRole.SPOUSE,
        target_id,
        RelationshipRole.SPOUSE,
    )


def _relationship_matches_edge(
    relationship: RelationshipClaim,
    edge: tuple[
        RelationshipType,
        str,
        RelationshipRole,
        str,
        RelationshipRole,
    ],
) -> bool:
    relationship_type, subject_id, subject_role, object_id, object_role = edge
    if relationship.relationship_type is not relationship_type:
        return False
    if relationship_type is RelationshipType.SPOUSE:
        return {
            relationship.subject_mention_id,
            relationship.object_mention_id,
        } == {subject_id, object_id}
    return (
        relationship.subject_mention_id == subject_id
        and relationship.subject_role is subject_role
        and relationship.object_mention_id == object_id
        and relationship.object_role is object_role
    )


def matching_relationships(
    *,
    relationships: list[RelationshipClaim],
    context: BoundedCoreferenceContext,
) -> list[RelationshipClaim]:
    edges = [
        _expected_edge(candidate_id, target_id, context.kinship.frame)
        for candidate_id in context.candidate_ids
        for target_id in context.target_ids
    ]
    return [
        relationship
        for relationship in relationships
        if context.segment_id in relationship.source_segment_ids
        and any(_relationship_matches_edge(relationship, edge) for edge in edges)
    ]


def trusted_existing_link_ids(result: ExtractionResult) -> set[str]:
    return {
        link.coreference_id
        for link in result.coreference_links
        if not (
            link.status is CoreferenceStatus.RESOLVED
            and link.method not in _TRUSTED_RESOLVED_METHODS
        )
    }


def clean_relationship_links(
    relationships: list[RelationshipClaim],
    trusted_link_ids: set[str],
) -> list[RelationshipClaim]:
    return [
        relationship.model_copy(
            update={
                "coreference_link_ids": [
                    link_id
                    for link_id in relationship.coreference_link_ids
                    if link_id in trusted_link_ids
                ]
            }
        )
        for relationship in relationships
    ]


def build_evidence(
    *,
    link_id: str,
    context_unit: TextUnit,
    anaphor_segment_id: str,
    anaphor_start: int,
    anaphor_end: int,
    mention_ids: list[str],
    evidence_class: EvidenceClass,
    transcript: TranscriptEnvelope,
    confidence: float,
) -> list[EvidenceSpan]:
    segment_by_id = {segment.segment_id: segment for segment in transcript.segments}
    anaphor_segment = segment_by_id[anaphor_segment_id]
    context_evidence_id = f"evidence_{safe_id(link_id)}_context"
    anaphor_evidence_id = f"evidence_{safe_id(link_id)}_anaphor"
    return [
        EvidenceSpan(
            evidence_id=context_evidence_id,
            segment_id=context_unit.segment_id,
            text=context_unit.text,
            start_char=context_unit.start,
            end_char=context_unit.end,
            evidence_class=evidence_class,
            purposes=[EvidencePurpose.CONTEXT, EvidencePurpose.COREFERENCE],
            mention_ids=list(dict.fromkeys(mention_ids)),
            coreference_link_ids=[link_id],
            confidence=confidence,
        ),
        EvidenceSpan(
            evidence_id=anaphor_evidence_id,
            segment_id=anaphor_segment_id,
            text=anaphor_segment.text[anaphor_start:anaphor_end],
            start_char=anaphor_start,
            end_char=anaphor_end,
            evidence_class=evidence_class,
            purposes=[EvidencePurpose.COREFERENCE, EvidencePurpose.CLAIM],
            mention_ids=list(dict.fromkeys(mention_ids)),
            coreference_link_ids=[link_id],
            confidence=confidence,
        ),
    ]


def status_for(context: BoundedCoreferenceContext) -> CoreferenceStatus:
    if context.resolved:
        return CoreferenceStatus.RESOLVED
    if len(context.candidate_ids) >= 2:
        return CoreferenceStatus.AMBIGUOUS
    return CoreferenceStatus.UNRESOLVED


def rule_id_for(
    context: BoundedCoreferenceContext,
    status: CoreferenceStatus,
) -> str:
    if (
        status is CoreferenceStatus.RESOLVED
        and context.anaphor.grammatical_number is GrammaticalNumber.PLURAL
    ):
        return "discourse.plural.explicit_pair.v1"
    if status is CoreferenceStatus.RESOLVED:
        return "discourse.singular.unique_antecedent.v1"
    if status is CoreferenceStatus.AMBIGUOUS:
        return "discourse.ambiguous_competing_antecedents.v1"
    return "discourse.unresolved.insufficient_candidates.v1"


def link_id_for(context: BoundedCoreferenceContext) -> str:
    identity = "\x1f".join(
        (
            context.segment_id,
            str(context.anaphor.start),
            str(context.anaphor.end),
            context.anaphor.surface,
            context.anaphor.grammatical_number.value,
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return (
        f"coreference_{safe_id(context.segment_id)}_"
        f"{context.anaphor.start}_{context.anaphor.grammatical_number.value}_{digest}"
    )


def update_relationships(
    *,
    relationships: list[RelationshipClaim],
    matching_ids: set[str],
    link_id: str,
    source_segment_ids: list[str],
    evidence_ids: list[str],
    transcript: TranscriptEnvelope,
) -> list[RelationshipClaim]:
    updated: list[RelationshipClaim] = []
    for relationship in relationships:
        if relationship.relationship_id not in matching_ids:
            updated.append(relationship)
            continue
        updated.append(
            relationship.model_copy(
                update={
                    "source_segment_ids": ordered_segment_ids(
                        [*relationship.source_segment_ids, *source_segment_ids],
                        transcript,
                    ),
                    "evidence_ids": list(
                        dict.fromkeys([*relationship.evidence_ids, *evidence_ids])
                    ),
                    "coreference_link_ids": list(
                        dict.fromkeys([*relationship.coreference_link_ids, link_id])
                    ),
                }
            )
        )
    return updated
