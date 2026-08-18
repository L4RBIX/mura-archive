from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import Field

from mura.deepseek.client import DeepSeekUsage
from mura.deepseek.discourse_telemetry import discourse_link_counters
from mura.deepseek.grounding_metrics import relationship_grounding_counters
from mura.domain.models import ExtractionResult, StrictModel, TranscriptEnvelope
from mura.evidence_recovery import EvidenceOffsetRecoveryMetrics
from mura.extraction_issues import privacy_safe_issues, safe_issue_counts
from mura.versioning import get_pipeline_versions


class RelationshipTelemetry(StrictModel):
    candidates: int = Field(ge=0)
    accepted: int = Field(ge=0)
    quarantined: int = Field(ge=0)
    acceptance_rate: float | None = Field(default=None, ge=0, le=1)


class ExtractionTelemetry(StrictModel):
    schema_version: str = "extraction-telemetry-v2"
    model: str
    finish_reason: str | None = None
    request_seconds: float = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    prompt_cache_hit_tokens: int | None = Field(default=None, ge=0)
    prompt_cache_miss_tokens: int | None = Field(default=None, ge=0)
    repair_attempted: bool
    repair_succeeded: bool
    fallback_used: bool = False
    accepted_object_count: int = Field(ge=0)
    quarantined_object_count: int = Field(ge=0)
    quarantined_items: int = Field(ge=0)
    evidence_closure_relationships: int = Field(ge=0)
    evidence_offset_recovery: dict[str, int]
    validation_issue_counts: dict[str, int]
    relationship_metrics: RelationshipTelemetry
    relationship_grounding_metrics: dict[str, int]
    coreference_metrics: dict[str, int]
    anchor_contract: dict[str, int | str]
    claim_contract: dict[str, int | str | dict[str, int]]
    prompt_version: str
    evidence_rule_version: str
    domain_schema_version: str
    pipeline_version: str
    extraction_issues: list[dict[str, Any]] = Field(default_factory=list)


def _accepted_object_count(result: ExtractionResult) -> int:
    return sum(
        len(items)
        for items in (
            result.people_mentions,
            result.relationship_claims,
            result.events,
            result.descriptions,
            result.stories,
            result.unresolved_questions,
        )
    )


def build_extraction_telemetry(
    *,
    raw: dict[str, Any],
    usage: DeepSeekUsage,
    result: ExtractionResult,
    extraction_issues: list[dict[str, Any]],
    evidence_closure_count: int,
    evidence_recovery: EvidenceOffsetRecoveryMetrics,
    transcript: TranscriptEnvelope,
    anchor_schema_version: str,
    allowed_segment_count: int,
    mention_anchor_count: int,
    lexical_annotation_count: int,
    repair_attempted: bool,
    repair_succeeded: bool,
) -> ExtractionTelemetry:
    raw_relationships = raw.get("relationship_claims", [])
    relationship_candidates = len(raw_relationships) if isinstance(raw_relationships, list) else 0
    accepted_relationship_ids = {item.relationship_id for item in result.relationship_claims}
    quarantined_relationship_ids = {
        issue.get("object_id")
        for issue in extraction_issues
        if issue.get("object_type") == "relationship" and issue.get("object_id") is not None
    }
    evidence_class_counts = Counter(
        item.evidence_class.value
        for item in [
            *result.people_mentions,
            *result.relationship_claims,
            *result.events,
            *result.descriptions,
            *result.stories,
            *result.unresolved_questions,
        ]
    )
    versions = get_pipeline_versions()
    return ExtractionTelemetry(
        model=usage.model,
        finish_reason=usage.finish_reason,
        request_seconds=usage.request_seconds,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        prompt_cache_hit_tokens=usage.prompt_cache_hit_tokens,
        prompt_cache_miss_tokens=usage.prompt_cache_miss_tokens,
        repair_attempted=repair_attempted,
        repair_succeeded=repair_succeeded,
        accepted_object_count=_accepted_object_count(result),
        quarantined_object_count=len(
            {
                (issue.get("object_type"), issue.get("object_id"))
                for issue in extraction_issues
                if issue.get("severity") in {"error", "fatal"}
                and issue.get("object_id") is not None
            }
        ),
        quarantined_items=len(extraction_issues),
        evidence_closure_relationships=evidence_closure_count,
        evidence_offset_recovery=evidence_recovery.to_dict(),
        validation_issue_counts=safe_issue_counts(extraction_issues),
        relationship_metrics=RelationshipTelemetry(
            candidates=relationship_candidates,
            accepted=len(accepted_relationship_ids),
            quarantined=len(quarantined_relationship_ids),
            acceptance_rate=(
                len(accepted_relationship_ids) / relationship_candidates
                if relationship_candidates
                else None
            ),
        ),
        relationship_grounding_metrics=relationship_grounding_counters(
            result=result,
            transcript=transcript,
            extraction_issues=privacy_safe_issues(extraction_issues),
        ),
        coreference_metrics=discourse_link_counters(result),
        anchor_contract={
            "schema_version": anchor_schema_version,
            "allowed_segments": allowed_segment_count,
            "mention_anchors": mention_anchor_count,
            "lexical_annotations": lexical_annotation_count,
        },
        claim_contract={
            "schema_version": result.schema_version,
            "evidence_spans": len(result.evidence_spans),
            "provenance_activities": len(result.provenance_activities),
            "coreference_links": len(result.coreference_links),
            "conflict_sets": len(result.conflict_sets),
            "evidence_class_counts": dict(sorted(evidence_class_counts.items())),
        },
        prompt_version=versions.extractor_prompt,
        evidence_rule_version=versions.evidence_rules,
        domain_schema_version=versions.domain_schema,
        pipeline_version=versions.pipeline,
        extraction_issues=privacy_safe_issues(extraction_issues),
    )
