from __future__ import annotations

import json
from pathlib import Path

from mura.evaluation.models import BenchmarkReport, PrecisionRecallF1, RatioMetric


def write_json_report(report: BenchmarkReport, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _format_prf(metric: PrecisionRecallF1) -> str:
    return (
        f"P={metric.precision:.3f}, R={metric.recall:.3f}, F1={metric.f1:.3f} "
        f"(TP={metric.true_positive}, FP={metric.false_positive}, "
        f"FN={metric.false_negative})"
    )


def _format_ratio(metric: RatioMetric) -> str:
    return f"{metric.value:.3f} ({metric.numerator}/{metric.denominator})"


def render_markdown_report(report: BenchmarkReport) -> str:
    summary = report.summary
    lines = [
        "# Mura ML Core Baseline",
        "",
        f"Manifest: `{report.manifest_path}`",
        "",
        "## Pipeline versions",
        "",
        "| Component | Version |",
        "|---|---|",
    ]
    lines.extend(
        f"| {component} | `{version}` |"
        for component, version in sorted(report.pipeline_versions.items())
    )
    lines.extend(
        [
            "",
            "## Aggregate metrics",
            "",
            f"- Cases: **{summary.case_count}**",
            f"- Person mentions: {_format_prf(summary.person_mentions)}",
            f"- Relationships: {_format_prf(summary.relationships)}",
            (
                "- Expected relationship quarantine: "
                f"{_format_prf(summary.quarantined_relationships)}"
            ),
            (f"- Expected object quarantine: {_format_prf(summary.quarantined_objects)}"),
            (
                "- Relationship direction accuracy: "
                f"{_format_ratio(summary.relationship_direction_accuracy)}"
            ),
            (f"- Provenance completeness: {_format_ratio(summary.provenance_completeness)}"),
            f"- Events: {_format_prf(summary.events)}",
            f"- Descriptions: {_format_prf(summary.descriptions)}",
            f"- Stories: {_format_prf(summary.stories)}",
            (f"- Event participant accuracy: {_format_ratio(summary.event_participant_accuracy)}"),
            (f"- Narrative factual support: {_format_ratio(summary.narrative_factual_support)}"),
            f"- Sensitive story recall: {_format_ratio(summary.sensitive_story_recall)}",
            f"- Unsupported event statements: **{summary.unsupported_event_statements}**",
            f"- Unsupported story statements: **{summary.unsupported_story_statements}**",
            (f"- Sensitivity underclassifications: **{summary.sensitivity_underclassifications}**"),
            f"- Duplicate semantic events: **{summary.duplicate_semantic_events}**",
            f"- Duplicate semantic stories: **{summary.duplicate_semantic_stories}**",
            (f"- Unknown segment references: **{summary.unknown_segment_references}**"),
            f"- Self relationships: **{summary.self_relationships}**",
            f"- Provenance violations: **{summary.provenance_violations}**",
            f"- Objects without evidence: **{summary.objects_without_evidence}**",
            f"- Invalid evidence spans: **{summary.invalid_evidence_spans}**",
            f"- Unsafe verification statuses: **{summary.unsafe_verification_statuses}**",
            f"- Unsafe story privacy: **{summary.unsafe_story_privacy}**",
            f"- Unknown issue codes: **{summary.unknown_issue_codes}**",
            f"- Missing required issue codes: **{summary.missing_required_issue_codes}**",
            f"- Fatal contract failures: **{summary.fatal_contract_failures}**",
            "",
            "## Cases",
            "",
            "| Case | Language | Relationships | Quarantine | Accepted | Quarantined |",
            "|---|---|---|---|---|---|",
        ]
    )
    for case in report.cases:
        accepted = ", ".join(case.accepted_relationship_ids) or "—"
        quarantined = ", ".join(case.quarantined_relationship_ids) or "—"
        lines.append(
            "| "
            f"{case.case_id} | {case.language.value} | "
            f"{case.relationships.f1:.3f} | "
            f"{case.quarantined_relationships.f1:.3f} | "
            f"{accepted} | {quarantined} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This report measures the deterministic validation layer against fixed extraction "
            "candidates. It does not measure live DeepSeek candidate generation or ASR quality.",
            "",
        ]
    )
    return "\n".join(lines)


def write_markdown_report(report: BenchmarkReport, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown_report(report), encoding="utf-8")
