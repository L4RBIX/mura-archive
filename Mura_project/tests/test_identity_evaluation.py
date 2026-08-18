from pathlib import Path

from mura.evaluation.identity import (
    evaluate_identity_gates,
    load_identity_gate_config,
    run_identity_evaluation,
)

ROOT = Path(__file__).resolve().parents[1]


def test_identity_release_gate_is_non_vacuous_and_zero_false_merge() -> None:
    report = run_identity_evaluation(
        coreference_path=ROOT / "benchmarks" / "coreference_v2.json",
        entity_path=ROOT / "benchmarks" / "entity_resolution_v2.json",
    )
    result = evaluate_identity_gates(
        report,
        load_identity_gate_config(ROOT / "benchmarks" / "identity_release_gates.json"),
    )

    assert result.passed is True
    assert result.measurements["coreference_case_count"] == 10
    assert result.measurements["entity_case_count"] == 14
    assert result.measurements["coreference_antecedent_accuracy"] == 1.0
    assert result.measurements["ambiguous_routing_accuracy"] == 1.0
    assert result.measurements["entity_false_merges"] == 0
    assert result.measurements["entity_false_splits"] == 0
    assert result.measurements["cross_quote_resolutions"] == 0
    assert result.measurements["verified_alias_collisions"] == 1
    assert result.measurements["mention_identity_collisions"] == 1
    assert result.measurements["inactive_relationships_ignored"] == 1
