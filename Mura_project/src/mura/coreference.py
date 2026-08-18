from __future__ import annotations

from dataclasses import dataclass

from mura.coreference_context import BoundedCoreferenceContext, bounded_coreference_contexts
from mura.coreference_materialization import (
    build_evidence,
    clean_relationship_links,
    link_id_for,
    matching_relationships,
    ordered_segment_ids,
    rule_id_for,
    status_for,
    trusted_existing_link_ids,
    update_relationships,
)
from mura.coreference_units import MAX_CONTEXT_CHARS
from mura.domain.models import (
    CoreferenceLink,
    CoreferenceMethod,
    CoreferenceStatus,
    EvidenceClass,
    ExtractionResult,
    RelationshipClaim,
    TranscriptEnvelope,
)


@dataclass(frozen=True)
class CoreferenceAugmentation:
    result: ExtractionResult
    changed_relationship_count: int
    generated_link_count: int


def _confidence(status: CoreferenceStatus) -> float:
    if status is CoreferenceStatus.RESOLVED:
        return 1.0
    if status is CoreferenceStatus.AMBIGUOUS:
        return 0.5
    return 0.0


def _evidence_class(status: CoreferenceStatus) -> EvidenceClass:
    if status is CoreferenceStatus.RESOLVED:
        return EvidenceClass.D_CONTEXT_RESOLVED
    return EvidenceClass.U_UNCERTAIN


def _build_link(
    *,
    context: BoundedCoreferenceContext,
    link_id: str,
    source_segment_ids: list[str],
    evidence_ids: list[str],
    status: CoreferenceStatus,
    confidence: float,
) -> CoreferenceLink:
    rule_id = rule_id_for(context, status)
    return CoreferenceLink(
        coreference_id=link_id,
        anaphor_text=context.anaphor.surface,
        source_segment_ids=source_segment_ids,
        evidence_ids=evidence_ids,
        status=status,
        method=CoreferenceMethod.DETERMINISTIC_DISCOURSE,
        grammatical_number=context.anaphor.grammatical_number,
        antecedent_mention_ids=(
            context.candidate_ids if status is CoreferenceStatus.RESOLVED else []
        ),
        candidate_mention_ids=context.candidate_ids,
        evidence_class=_evidence_class(status),
        confidence=confidence,
        reason=(
            f"{rule_id}: current unit plus at most one preceding unit; "
            f"max_context_chars={MAX_CONTEXT_CHARS}; "
            f"candidate_count={len(context.candidate_ids)}"
        ),
    )


def augment_bounded_coreference(
    result: ExtractionResult,
    transcript: TranscriptEnvelope,
) -> CoreferenceAugmentation:
    """Materialize deterministic links inside two adjacent units and 420 characters."""

    relationships: list[RelationshipClaim] = clean_relationship_links(
        list(result.relationship_claims),
        trusted_existing_link_ids(result),
    )
    links = list(result.coreference_links)
    evidence = list(result.evidence_spans)
    existing_link_ids = {link.coreference_id for link in links}
    existing_evidence_ids = {item.evidence_id for item in evidence}
    changed_relationship_ids: set[str] = set()
    generated_link_count = 0

    for context in bounded_coreference_contexts(
        people=result.people_mentions,
        transcript=transcript,
    ):
        matching = matching_relationships(
            relationships=relationships,
            context=context,
        )
        status = status_for(context)
        if status is not CoreferenceStatus.RESOLVED and not matching:
            continue
        link_id = link_id_for(context)
        if link_id in existing_link_ids:
            continue

        confidence = _confidence(status)
        evidence_class = _evidence_class(status)
        source_segment_ids = ordered_segment_ids(
            [context.candidate_context.segment_id, context.segment_id],
            transcript,
        )
        generated_evidence = build_evidence(
            link_id=link_id,
            context_unit=context.candidate_context,
            anaphor_segment_id=context.segment_id,
            anaphor_start=context.anaphor.start,
            anaphor_end=context.anaphor.end,
            mention_ids=[*context.candidate_ids, *context.target_ids],
            evidence_class=evidence_class,
            transcript=transcript,
            confidence=confidence,
        )
        if any(item.evidence_id in existing_evidence_ids for item in generated_evidence):
            continue

        link = _build_link(
            context=context,
            link_id=link_id,
            source_segment_ids=source_segment_ids,
            evidence_ids=[item.evidence_id for item in generated_evidence],
            status=status,
            confidence=confidence,
        )
        links.append(link)
        evidence.extend(generated_evidence)
        existing_link_ids.add(link_id)
        existing_evidence_ids.update(item.evidence_id for item in generated_evidence)
        generated_link_count += 1

        matching_ids = {relationship.relationship_id for relationship in matching}
        if not matching_ids:
            continue
        relationships = update_relationships(
            relationships=relationships,
            matching_ids=matching_ids,
            link_id=link_id,
            source_segment_ids=source_segment_ids,
            evidence_ids=[item.evidence_id for item in generated_evidence],
            transcript=transcript,
        )
        changed_relationship_ids.update(matching_ids)

    updated = result.model_copy(
        update={
            "evidence_spans": evidence,
            "coreference_links": links,
            "relationship_claims": relationships,
        }
    )
    return CoreferenceAugmentation(
        result=updated,
        changed_relationship_count=len(changed_relationship_ids),
        generated_link_count=generated_link_count,
    )
