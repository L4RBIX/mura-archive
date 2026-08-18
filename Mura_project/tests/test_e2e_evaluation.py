from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mura.evaluation.e2e import (
    evaluate_e2e_gates,
    load_e2e_dataset,
    load_e2e_gate_config,
    run_e2e_evaluation,
)
from mura.evaluation.e2e_live import (
    LiveE2ECaseRuntime,
    LiveE2EGateConfig,
    LiveE2EManifest,
    LiveE2EReport,
    _runtime,
    evaluate_live_e2e_gates,
)
from mura.evaluation.ml_release import run_ml_release
from mura.smoke import _synthetic_result


@pytest.fixture(scope="module")
def offline_release_report():
    return run_ml_release(Path("benchmarks/release/ml_release_manifest.json"))


def _model_digest(model) -> str:
    encoded = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_offline_e2e_gate_runs_real_pipeline_with_frozen_external_stages() -> None:
    dataset = load_e2e_dataset(Path("benchmarks/e2e_pipeline_v1.json"))
    report = run_e2e_evaluation(dataset)
    gate = evaluate_e2e_gates(
        report,
        load_e2e_gate_config(Path("benchmarks/e2e_release_gates.json")),
    )

    assert gate.passed is True, gate.failures
    assert report.external_stages_frozen is True
    assert report.summary.case_count == 4
    assert report.summary.deterministic_replay.value == 1.0
    assert report.summary.provenance_completeness.value == 1.0
    assert report.summary.cleaner_fallback_cases >= 1
    assert report.summary.extractor_repair_cases >= 1
    assert report.summary.focused_partial_failure_cases >= 1
    assert report.summary.review_resolution_cases >= 1
    assert report.summary.maximum_model_calls_observed <= 6
    assert all(case.output_digest != "0" * 64 for case in report.cases)


def test_offline_e2e_fails_closed_when_provider_stage_order_is_tampered(tmp_path: Path) -> None:
    payload = json.loads(Path("benchmarks/e2e_pipeline_v1.json").read_text(encoding="utf-8"))
    payload["cases"][0]["provider_responses"][0]["stage"] = "events"
    dataset_path = tmp_path / "tampered.json"
    dataset_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = run_e2e_evaluation(load_e2e_dataset(dataset_path))
    gate = evaluate_e2e_gates(
        report,
        load_e2e_gate_config(Path("benchmarks/e2e_release_gates.json")),
    )

    assert gate.passed is False
    assert report.cases[0].passed is False
    assert report.summary.fatal_case_failures >= 1


def test_composite_offline_release_gate_is_deterministic_and_version_consistent(
    offline_release_report,
) -> None:
    report = offline_release_report

    assert report.offline_release_candidate_passed is True, report.failures
    assert report.component_passed == {
        "core": True,
        "identity": True,
        "asr_contract": True,
        "offline_e2e": True,
    }
    assert report.version_consistency is True
    assert report.live_evaluation_required is True
    assert report.component_report_sha256 == {
        "core": _model_digest(report.core),
        "identity": _model_digest(report.identity),
        "asr_contract": _model_digest(report.asr),
        "offline_e2e": _model_digest(report.e2e),
    }


def test_live_runtime_counts_cleaner_repair_and_records_provider_models() -> None:
    result = _synthetic_result().model_copy(
        update={
            "processing": {
                "total_seconds": 1.25,
                "cleaner_usage": {
                    "model": "cleaner-model",
                    "repair_attempted": True,
                    "fallback_used": False,
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                },
                "extractor_usage": {
                    "model": "extractor-model",
                    "focused_passes": [
                        {"request_count": 1},
                        {"request_count": 2},
                        {"request_count": 1},
                    ],
                    "focused_partial_failures": 0,
                    "prompt_tokens": 20,
                    "completion_tokens": 8,
                    "total_tokens": 28,
                },
            }
        }
    )

    runtime = _runtime("case_1", result)

    assert runtime.model_calls == 6
    assert runtime.provider_models == ["cleaner-model", "extractor-model"]
    assert runtime.prompt_tokens == 30
    assert runtime.total_tokens == 42


def test_live_gate_fails_closed_for_unknown_commit_and_case_set_mismatch(
    offline_release_report,
) -> None:
    offline = offline_release_report
    report = LiveE2EReport(
        dataset_id="live-test",
        source_type="approved_private",
        license_or_consent="consent-record-test",
        pipeline_versions=offline.pipeline_versions,
        asr=offline.asr,
        ml=offline.core,
        runtimes=[
            LiveE2ECaseRuntime(
                case_id=item.case_id,
                pipeline_seconds=1.0,
                asr_seconds=0.5,
                cleaner_fallback_used=False,
                focused_partial_failures=0,
                model_calls=4,
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                provider_models=["deepseek-test"],
            )
            for item in offline.asr.cases
        ],
        source_commit="local-uncommitted-worktree",
    )
    config = LiveE2EGateConfig(
        minimum_case_count=1,
        minimum_language_case_count={},
        maximum_word_error_rate=1.0,
        maximum_character_error_rate=1.0,
        minimum_person_f1=0.0,
        minimum_relationship_precision=0.0,
        minimum_relationship_recall=0.0,
        minimum_provenance_completeness=0.0,
        maximum_unsafe_verification_statuses=100,
        maximum_unsafe_story_privacy=100,
        maximum_fatal_contract_failures=100,
        maximum_model_calls_per_case=10,
        maximum_pipeline_seconds_per_case=10.0,
        maximum_asr_seconds_per_case=10.0,
    )

    gate = evaluate_live_e2e_gates(report, config)

    assert gate.passed is False
    assert gate.measurements["source_commit_invalid"] == 1
    assert gate.measurements["case_id_mismatches"] > 0
    assert any("source_commit_invalid" in failure for failure in gate.failures)
    assert any("case_id_mismatches" in failure for failure in gate.failures)


def test_live_manifest_rejects_path_traversal() -> None:
    payload = {
        "dataset_id": "unsafe",
        "source_type": "approved_private",
        "license_or_consent": "test consent",
        "cases": [
            {
                "case_id": "case_1",
                "language": "ru",
                "audio_path": "../private.wav",
                "reference_text": "Ерлан пришёл",
                "speaker_id": "speaker_1",
                "speaker_name": "Айжан",
                "gold": {},
            }
        ],
    }

    try:
        LiveE2EManifest.model_validate(payload)
    except ValidationError as exc:
        assert "audio_path must stay inside" in str(exc)
    else:
        raise AssertionError("path traversal must be rejected")
