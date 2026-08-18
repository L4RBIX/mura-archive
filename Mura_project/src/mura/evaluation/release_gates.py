from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field

from mura.domain.models import StrictModel
from mura.evaluation.models import BenchmarkReport


class ReleaseGateConfig(StrictModel):
    schema_version: str = "release-gates-v4"
    minimum_case_count: int = Field(ge=1)
    minimum_adversarial_case_count: int = Field(ge=1)
    minimum_person_f1: float = Field(ge=0, le=1)
    minimum_relationship_precision: float = Field(ge=0, le=1)
    minimum_relationship_recall: float = Field(ge=0, le=1)
    minimum_quarantine_recall: float = Field(ge=0, le=1)
    minimum_object_quarantine_recall: float = Field(default=1.0, ge=0, le=1)
    minimum_direction_accuracy: float = Field(ge=0, le=1)
    minimum_provenance_completeness: float = Field(ge=0, le=1)
    maximum_unknown_segment_references: int = Field(ge=0)
    maximum_self_relationships: int = Field(ge=0)
    maximum_adversarial_relationship_false_positives: int = Field(ge=0)
    maximum_adversarial_quarantine_false_negatives: int = Field(ge=0)
    maximum_provenance_violations: int = Field(default=0, ge=0)
    maximum_objects_without_evidence: int = Field(default=0, ge=0)
    maximum_invalid_evidence_spans: int = Field(default=0, ge=0)
    maximum_unsafe_verification_statuses: int = Field(default=0, ge=0)
    maximum_unsafe_story_privacy: int = Field(default=0, ge=0)
    maximum_unknown_issue_codes: int = Field(default=0, ge=0)
    maximum_missing_required_issue_codes: int = Field(default=0, ge=0)
    maximum_fatal_contract_failures: int = Field(default=0, ge=0)
    minimum_uncertainty_scope_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_temporal_kind_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_relationship_state_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_event_precision: float = Field(default=1.0, ge=0, le=1)
    minimum_event_recall: float = Field(default=1.0, ge=0, le=1)
    minimum_description_precision: float = Field(default=1.0, ge=0, le=1)
    minimum_description_recall: float = Field(default=1.0, ge=0, le=1)
    minimum_story_precision: float = Field(default=1.0, ge=0, le=1)
    minimum_story_recall: float = Field(default=1.0, ge=0, le=1)
    minimum_event_participant_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_narrative_factual_support: float = Field(default=1.0, ge=0, le=1)
    minimum_sensitive_story_recall: float = Field(default=1.0, ge=0, le=1)
    maximum_unsupported_event_statements: int = Field(default=0, ge=0)
    maximum_unsupported_story_statements: int = Field(default=0, ge=0)
    maximum_sensitivity_underclassifications: int = Field(default=0, ge=0)
    maximum_duplicate_semantic_events: int = Field(default=0, ge=0)
    maximum_duplicate_semantic_stories: int = Field(default=0, ge=0)
    maximum_approximate_dates_exactified: int = Field(default=0, ge=0)
    maximum_invalid_calendar_dates_accepted: int = Field(default=0, ge=0)
    maximum_unresolved_relative_dates_absolutized: int = Field(default=0, ge=0)
    maximum_negated_relationship_false_positives: int = Field(default=0, ge=0)
    maximum_figurative_relationship_false_positives: int = Field(default=0, ge=0)
    maximum_former_relationships_active: int = Field(default=0, ge=0)
    maximum_ended_relationships_active: int = Field(default=0, ge=0)


class ReleaseGateResult(StrictModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)
    measurements: dict[str, int | float] = Field(default_factory=dict)


def _read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def load_release_gate_config(path: str | Path) -> ReleaseGateConfig:
    return ReleaseGateConfig.model_validate(_read_json(path))


def evaluate_release_gates(
    report: BenchmarkReport,
    config: ReleaseGateConfig,
) -> ReleaseGateResult:
    adversarial = [case for case in report.cases if "adversarial" in case.construction_tags]
    adversarial_relationship_false_positives = sum(
        case.relationships.false_positive for case in adversarial
    )
    adversarial_quarantine_false_negatives = sum(
        case.quarantined_relationships.false_negative for case in adversarial
    )

    measurements: dict[str, int | float] = {
        "case_count": report.summary.case_count,
        "adversarial_case_count": len(adversarial),
        "person_f1": report.summary.person_mentions.f1,
        "relationship_precision": report.summary.relationships.precision,
        "relationship_recall": report.summary.relationships.recall,
        "quarantine_recall": report.summary.quarantined_relationships.recall,
        "object_quarantine_recall": report.summary.quarantined_objects.recall,
        "direction_accuracy": report.summary.relationship_direction_accuracy.value,
        "provenance_completeness": report.summary.provenance_completeness.value,
        "unknown_segment_references": report.summary.unknown_segment_references,
        "self_relationships": report.summary.self_relationships,
        "adversarial_relationship_false_positives": adversarial_relationship_false_positives,
        "adversarial_quarantine_false_negatives": adversarial_quarantine_false_negatives,
        "provenance_violations": report.summary.provenance_violations,
        "objects_without_evidence": report.summary.objects_without_evidence,
        "invalid_evidence_spans": report.summary.invalid_evidence_spans,
        "unsafe_verification_statuses": report.summary.unsafe_verification_statuses,
        "unsafe_story_privacy": report.summary.unsafe_story_privacy,
        "unknown_issue_codes": report.summary.unknown_issue_codes,
        "missing_required_issue_codes": report.summary.missing_required_issue_codes,
        "fatal_contract_failures": report.summary.fatal_contract_failures,
        "uncertainty_scope_accuracy": report.summary.uncertainty_scope_accuracy.value,
        "temporal_kind_accuracy": report.summary.temporal_kind_accuracy.value,
        "relationship_state_accuracy": report.summary.relationship_state_accuracy.value,
        "event_precision": report.summary.events.precision,
        "event_recall": report.summary.events.recall,
        "description_precision": report.summary.descriptions.precision,
        "description_recall": report.summary.descriptions.recall,
        "story_precision": report.summary.stories.precision,
        "story_recall": report.summary.stories.recall,
        "event_participant_accuracy": report.summary.event_participant_accuracy.value,
        "narrative_factual_support": report.summary.narrative_factual_support.value,
        "sensitive_story_recall": report.summary.sensitive_story_recall.value,
        "unsupported_event_statements": report.summary.unsupported_event_statements,
        "unsupported_story_statements": report.summary.unsupported_story_statements,
        "sensitivity_underclassifications": report.summary.sensitivity_underclassifications,
        "duplicate_semantic_events": report.summary.duplicate_semantic_events,
        "duplicate_semantic_stories": report.summary.duplicate_semantic_stories,
        "approximate_dates_exactified": report.summary.approximate_dates_exactified,
        "invalid_calendar_dates_accepted": report.summary.invalid_calendar_dates_accepted,
        "unresolved_relative_dates_absolutized": (
            report.summary.unresolved_relative_dates_absolutized
        ),
        "negated_relationship_false_positives": report.summary.negated_relationship_false_positives,
        "figurative_relationship_false_positives": (
            report.summary.figurative_relationship_false_positives
        ),
        "former_relationships_active": report.summary.former_relationships_active,
        "ended_relationships_active": report.summary.ended_relationships_active,
    }

    failures: list[str] = []

    def require_minimum(name: str, threshold: int | float) -> None:
        value = measurements[name]
        if value < threshold:
            failures.append(f"{name}={value} is below required minimum {threshold}")

    def require_maximum(name: str, threshold: int | float) -> None:
        value = measurements[name]
        if value > threshold:
            failures.append(f"{name}={value} exceeds allowed maximum {threshold}")

    require_minimum("case_count", config.minimum_case_count)
    require_minimum("adversarial_case_count", config.minimum_adversarial_case_count)
    require_minimum("person_f1", config.minimum_person_f1)
    require_minimum("relationship_precision", config.minimum_relationship_precision)
    require_minimum("relationship_recall", config.minimum_relationship_recall)
    require_minimum("quarantine_recall", config.minimum_quarantine_recall)
    require_minimum("object_quarantine_recall", config.minimum_object_quarantine_recall)
    require_minimum("direction_accuracy", config.minimum_direction_accuracy)
    require_minimum("provenance_completeness", config.minimum_provenance_completeness)
    require_maximum(
        "unknown_segment_references",
        config.maximum_unknown_segment_references,
    )
    require_maximum("self_relationships", config.maximum_self_relationships)
    require_maximum(
        "adversarial_relationship_false_positives",
        config.maximum_adversarial_relationship_false_positives,
    )
    require_maximum(
        "adversarial_quarantine_false_negatives",
        config.maximum_adversarial_quarantine_false_negatives,
    )
    require_maximum("provenance_violations", config.maximum_provenance_violations)
    require_maximum("objects_without_evidence", config.maximum_objects_without_evidence)
    require_maximum("invalid_evidence_spans", config.maximum_invalid_evidence_spans)
    require_maximum(
        "unsafe_verification_statuses",
        config.maximum_unsafe_verification_statuses,
    )
    require_maximum("unsafe_story_privacy", config.maximum_unsafe_story_privacy)
    require_maximum("unknown_issue_codes", config.maximum_unknown_issue_codes)
    require_maximum(
        "missing_required_issue_codes",
        config.maximum_missing_required_issue_codes,
    )
    require_maximum("fatal_contract_failures", config.maximum_fatal_contract_failures)
    require_minimum("uncertainty_scope_accuracy", config.minimum_uncertainty_scope_accuracy)
    require_minimum("temporal_kind_accuracy", config.minimum_temporal_kind_accuracy)
    require_minimum("relationship_state_accuracy", config.minimum_relationship_state_accuracy)
    require_minimum("event_precision", config.minimum_event_precision)
    require_minimum("event_recall", config.minimum_event_recall)
    require_minimum("description_precision", config.minimum_description_precision)
    require_minimum("description_recall", config.minimum_description_recall)
    require_minimum("story_precision", config.minimum_story_precision)
    require_minimum("story_recall", config.minimum_story_recall)
    require_minimum("event_participant_accuracy", config.minimum_event_participant_accuracy)
    require_minimum("narrative_factual_support", config.minimum_narrative_factual_support)
    require_minimum("sensitive_story_recall", config.minimum_sensitive_story_recall)
    require_maximum("unsupported_event_statements", config.maximum_unsupported_event_statements)
    require_maximum("unsupported_story_statements", config.maximum_unsupported_story_statements)
    require_maximum(
        "sensitivity_underclassifications", config.maximum_sensitivity_underclassifications
    )
    require_maximum("duplicate_semantic_events", config.maximum_duplicate_semantic_events)
    require_maximum("duplicate_semantic_stories", config.maximum_duplicate_semantic_stories)
    require_maximum(
        "approximate_dates_exactified",
        config.maximum_approximate_dates_exactified,
    )
    require_maximum(
        "invalid_calendar_dates_accepted",
        config.maximum_invalid_calendar_dates_accepted,
    )
    require_maximum(
        "unresolved_relative_dates_absolutized",
        config.maximum_unresolved_relative_dates_absolutized,
    )
    require_maximum(
        "negated_relationship_false_positives",
        config.maximum_negated_relationship_false_positives,
    )
    require_maximum(
        "figurative_relationship_false_positives",
        config.maximum_figurative_relationship_false_positives,
    )
    require_maximum("former_relationships_active", config.maximum_former_relationships_active)
    require_maximum("ended_relationships_active", config.maximum_ended_relationships_active)
    return ReleaseGateResult(passed=not failures, failures=failures, measurements=measurements)


def render_release_gate_result(result: ReleaseGateResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    lines = [f"# Mura Release Gate: {status}", ""]
    for name, value in sorted(result.measurements.items()):
        lines.append(f"- {name}: `{value}`")
    if result.failures:
        lines.extend(["", "## Failures"])
        lines.extend(f"- {failure}" for failure in result.failures)
    return "\n".join(lines)
