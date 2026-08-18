from __future__ import annotations

from dataclasses import replace

from mura import _relationship_evidence_impl as _impl
from mura.domain.models import (
    EvidenceClass,
    PersonMention,
    RelationshipClaim,
    TranscriptEnvelope,
)

RelationshipEvidenceAnalysis = _impl.RelationshipEvidenceAnalysis
contains_exact_surface = _impl.contains_exact_surface
contains_surface = _impl.contains_surface
exactly_named_people = _impl.exactly_named_people
explicitly_named_people = _impl.explicitly_named_people
has_first_person_reference = _impl.has_first_person_reference
joined_segment_text = _impl.joined_segment_text
normalize_evidence = _impl.normalize_evidence
person_name_surfaces = _impl.person_name_surfaces
relationship_grounding_metrics = _impl.relationship_grounding_metrics
speaker_mentions = _impl.speaker_mentions

__all__ = [
    "RelationshipEvidenceAnalysis",
    "analyze_relationship_evidence",
    "contains_exact_surface",
    "contains_surface",
    "exactly_named_people",
    "explicitly_named_people",
    "has_first_person_reference",
    "joined_segment_text",
    "normalize_evidence",
    "person_name_surfaces",
    "relationship_grounding_metrics",
    "speaker_mentions",
]


def analyze_relationship_evidence(
    *,
    relationship: RelationshipClaim,
    transcript: TranscriptEnvelope,
    people: list[PersonMention],
    speaker_name: str,
    resolved_coreference_antecedent_ids: set[str] | None = None,
) -> RelationshipEvidenceAnalysis:
    analysis = _impl.analyze_relationship_evidence(
        relationship=relationship,
        transcript=transcript,
        people=people,
        speaker_name=speaker_name,
        resolved_coreference_antecedent_ids=resolved_coreference_antecedent_ids,
    )
    resolved = resolved_coreference_antecedent_ids or set()
    endpoints = {
        relationship.subject_mention_id,
        relationship.object_mention_id,
    }
    if not endpoints.intersection(resolved):
        return analysis
    if analysis.conflicting_signal_rule_ids:
        return analysis
    return replace(
        analysis,
        evidence_class=EvidenceClass.D_CONTEXT_RESOLVED.value,
        role_consistent=None,
        grounding_decision="resolved_coreference",
        auto_accept_eligible=False,
    )
