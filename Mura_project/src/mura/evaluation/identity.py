from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from mura.domain.models import StrictModel
from mura.evaluation.coreference import CoreferenceBenchmarkReport, run_coreference_benchmark
from mura.evaluation.entity_resolution import (
    EntityResolutionBenchmarkReport,
    run_entity_resolution_benchmark,
)


class IdentityReleaseGateConfig(StrictModel):
    schema_version: str = "identity-release-gates-v1"
    minimum_coreference_case_count: int = Field(default=8, ge=1)
    minimum_entity_case_count: int = Field(default=12, ge=1)
    minimum_coreference_status_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_coreference_antecedent_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_ambiguous_routing_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_entity_status_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_entity_identity_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_entity_review_routing_accuracy: float = Field(default=1.0, ge=0, le=1)
    maximum_unsupported_resolved_coreference: int = Field(default=0, ge=0)
    maximum_cross_quote_resolutions: int = Field(default=0, ge=0)
    maximum_forbidden_resolved_anaphors: int = Field(default=0, ge=0)
    maximum_entity_false_merges: int = Field(default=0, ge=0)
    maximum_entity_false_splits: int = Field(default=0, ge=0)
    maximum_cross_family_merges: int = Field(default=0, ge=0)


class IdentityEvaluationReport(StrictModel):
    report_schema_version: str = "identity-evaluation-report-v1"
    coreference: CoreferenceBenchmarkReport
    entity_resolution: EntityResolutionBenchmarkReport


class IdentityGateResult(StrictModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)
    measurements: dict[str, int | float] = Field(default_factory=dict)


def run_identity_evaluation(
    *,
    coreference_path: Path,
    entity_path: Path,
) -> IdentityEvaluationReport:
    return IdentityEvaluationReport(
        coreference=run_coreference_benchmark(coreference_path),
        entity_resolution=run_entity_resolution_benchmark(entity_path),
    )


def load_identity_gate_config(path: Path) -> IdentityReleaseGateConfig:
    return IdentityReleaseGateConfig.model_validate_json(path.read_text(encoding="utf-8"))


def evaluate_identity_gates(
    report: IdentityEvaluationReport,
    config: IdentityReleaseGateConfig,
) -> IdentityGateResult:
    coref = report.coreference.summary
    entity = report.entity_resolution.summary
    measurements: dict[str, int | float] = {
        "coreference_case_count": coref.case_count,
        "entity_case_count": entity.case_count,
        "coreference_status_accuracy": coref.status_accuracy,
        "coreference_antecedent_accuracy": coref.antecedent_accuracy,
        "ambiguous_routing_accuracy": coref.ambiguous_routing_accuracy,
        "entity_status_accuracy": entity.status_accuracy,
        "entity_identity_accuracy": entity.identity_accuracy,
        "entity_review_routing_accuracy": entity.review_routing_accuracy,
        "unsupported_resolved_coreference": coref.unsupported_resolved_links,
        "cross_quote_resolutions": coref.cross_quote_resolutions,
        "forbidden_resolved_anaphors": coref.forbidden_resolved_anaphors,
        "entity_false_merges": entity.false_merges,
        "entity_false_splits": entity.false_splits,
        "cross_family_merges": entity.cross_family_merges,
        "verified_alias_collisions": entity.verified_alias_collisions,
        "mention_identity_collisions": entity.mention_identity_collisions,
        "inactive_relationships_ignored": entity.inactive_relationships_ignored,
    }
    failures: list[str] = []

    def minimum(name: str, threshold: int | float) -> None:
        if measurements[name] < threshold:
            failures.append(f"{name}={measurements[name]} is below minimum {threshold}")

    def maximum(name: str, threshold: int | float) -> None:
        if measurements[name] > threshold:
            failures.append(f"{name}={measurements[name]} exceeds maximum {threshold}")

    minimum("coreference_case_count", config.minimum_coreference_case_count)
    minimum("entity_case_count", config.minimum_entity_case_count)
    minimum("coreference_status_accuracy", config.minimum_coreference_status_accuracy)
    minimum("coreference_antecedent_accuracy", config.minimum_coreference_antecedent_accuracy)
    minimum("ambiguous_routing_accuracy", config.minimum_ambiguous_routing_accuracy)
    minimum("entity_status_accuracy", config.minimum_entity_status_accuracy)
    minimum("entity_identity_accuracy", config.minimum_entity_identity_accuracy)
    minimum("entity_review_routing_accuracy", config.minimum_entity_review_routing_accuracy)
    maximum("unsupported_resolved_coreference", config.maximum_unsupported_resolved_coreference)
    maximum("cross_quote_resolutions", config.maximum_cross_quote_resolutions)
    maximum("forbidden_resolved_anaphors", config.maximum_forbidden_resolved_anaphors)
    maximum("entity_false_merges", config.maximum_entity_false_merges)
    maximum("entity_false_splits", config.maximum_entity_false_splits)
    maximum("cross_family_merges", config.maximum_cross_family_merges)
    return IdentityGateResult(passed=not failures, failures=failures, measurements=measurements)


def render_identity_report(report: IdentityEvaluationReport, gate: IdentityGateResult) -> str:
    lines = ["# Mura Identity Evaluation", ""]
    for name, value in sorted(gate.measurements.items()):
        lines.append(f"- {name}: `{value}`")
    lines.extend(["", f"## Gate: {'PASS' if gate.passed else 'FAIL'}"])
    lines.extend(f"- {failure}" for failure in gate.failures)
    return "\n".join(lines)


def write_identity_json(report: IdentityEvaluationReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
