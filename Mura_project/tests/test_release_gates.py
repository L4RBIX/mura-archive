from __future__ import annotations

from pathlib import Path

from mura.evaluation.cli import main
from mura.evaluation.release_gates import (
    ReleaseGateConfig,
    evaluate_release_gates,
    load_release_gate_config,
)
from mura.evaluation.runner import run_benchmark

ROOT = Path(__file__).resolve().parents[1]
RELEASE_MANIFEST = ROOT / "benchmarks" / "release_manifest.json"
GATES = ROOT / "benchmarks" / "release_gates.json"


def test_adversarial_dataset_is_enabled_and_release_gates_pass() -> None:
    report = run_benchmark(RELEASE_MANIFEST)
    adversarial = [case for case in report.cases if "adversarial" in case.construction_tags]

    assert report.summary.case_count == 32
    assert len(adversarial) == 26
    assert {case.split.value for case in adversarial} == {"test"}

    result = evaluate_release_gates(report, load_release_gate_config(GATES))
    assert result.passed is True
    assert result.failures == []
    assert result.measurements["adversarial_relationship_false_positives"] == 0
    assert result.measurements["adversarial_quarantine_false_negatives"] == 0
    assert result.measurements["object_quarantine_recall"] == 1.0
    assert result.measurements["provenance_violations"] == 0
    assert result.measurements["objects_without_evidence"] == 0
    assert result.measurements["invalid_evidence_spans"] == 0
    assert result.measurements["unsafe_verification_statuses"] == 0
    assert result.measurements["unsafe_story_privacy"] == 0
    assert result.measurements["unknown_issue_codes"] == 0
    assert result.measurements["missing_required_issue_codes"] == 0
    assert result.measurements["fatal_contract_failures"] == 0
    assert result.measurements["event_precision"] == 1.0
    assert result.measurements["event_recall"] == 1.0
    assert result.measurements["description_precision"] == 1.0
    assert result.measurements["description_recall"] == 1.0
    assert result.measurements["story_precision"] == 1.0
    assert result.measurements["story_recall"] == 1.0
    assert result.measurements["event_participant_accuracy"] == 1.0
    assert result.measurements["narrative_factual_support"] == 1.0
    assert result.measurements["sensitive_story_recall"] == 1.0
    assert result.measurements["unsupported_event_statements"] == 0
    assert result.measurements["unsupported_story_statements"] == 0
    assert result.measurements["sensitivity_underclassifications"] == 0
    assert result.measurements["duplicate_semantic_events"] == 0
    assert result.measurements["duplicate_semantic_stories"] == 0


def test_release_gate_reports_regression_without_hiding_measurement() -> None:
    report = run_benchmark(RELEASE_MANIFEST)
    strict = ReleaseGateConfig(
        minimum_case_count=100,
        minimum_adversarial_case_count=20,
        minimum_person_f1=1.0,
        minimum_relationship_precision=1.0,
        minimum_relationship_recall=1.0,
        minimum_quarantine_recall=1.0,
        minimum_direction_accuracy=1.0,
        minimum_provenance_completeness=1.0,
        maximum_unknown_segment_references=0,
        maximum_self_relationships=0,
        maximum_adversarial_relationship_false_positives=0,
        maximum_adversarial_quarantine_false_negatives=0,
    )

    result = evaluate_release_gates(report, strict)
    assert result.passed is False
    assert any("case_count" in failure for failure in result.failures)
    assert result.measurements["case_count"] == 32


def test_cli_returns_nonzero_for_failed_release_gate(tmp_path: Path) -> None:
    gate_path = tmp_path / "impossible.json"
    gate_path.write_text(
        """{
          "schema_version": "release-gates-v2",
          "minimum_case_count": 999,
          "minimum_adversarial_case_count": 999,
          "minimum_person_f1": 1.0,
          "minimum_relationship_precision": 1.0,
          "minimum_relationship_recall": 1.0,
          "minimum_quarantine_recall": 1.0,
          "minimum_direction_accuracy": 1.0,
          "minimum_provenance_completeness": 1.0,
          "maximum_unknown_segment_references": 0,
          "maximum_self_relationships": 0,
          "maximum_adversarial_relationship_false_positives": 0,
          "maximum_adversarial_quarantine_false_negatives": 0
        }""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--manifest",
            str(RELEASE_MANIFEST),
            "--release-gates",
            str(gate_path),
        ]
    )
    assert exit_code == 2
