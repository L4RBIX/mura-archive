from pathlib import Path

from mura.evaluation.runner import run_benchmark

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "pr16_manifest.json"


def test_pr16_multilingual_development_benchmark_passes() -> None:
    report = run_benchmark(MANIFEST)
    summary = report.summary

    assert summary.case_count == 6
    assert summary.person_mentions.true_positive == 13
    assert summary.person_mentions.false_positive == 0
    assert summary.person_mentions.false_negative == 0
    assert summary.person_mentions.f1 == 1.0

    assert summary.relationships.true_positive == 5
    assert summary.relationships.false_positive == 0
    assert summary.relationships.false_negative == 0
    assert summary.relationships.precision == 1.0
    assert summary.relationships.recall == 1.0
    assert summary.relationships.f1 == 1.0

    assert summary.quarantined_relationships.true_positive == 1
    assert summary.quarantined_relationships.false_positive == 0
    assert summary.quarantined_relationships.false_negative == 0
    assert summary.quarantined_relationships.f1 == 1.0

    assert summary.relationship_direction_accuracy.numerator == 5
    assert summary.relationship_direction_accuracy.denominator == 5
    assert summary.relationship_direction_accuracy.value == 1.0
    assert summary.provenance_completeness.value == 1.0
    assert summary.unknown_segment_references == 0
    assert summary.self_relationships == 0


def test_pr16_benchmark_keeps_third_person_possessive_quarantined() -> None:
    report = run_benchmark(MANIFEST)
    cases = {case.case_id: case for case in report.cases}

    ambiguous = cases["pr16_ru_ambiguous_possessive"]
    assert ambiguous.accepted_relationship_ids == []
    assert ambiguous.quarantined_relationship_ids == ["relationship_001"]

    mixed = cases["pr16_mixed_speaker_son"]
    assert mixed.accepted_relationship_ids == ["relationship_001"]
    assert mixed.quarantined_relationship_ids == []
