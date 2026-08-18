from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mura.evaluation.asr import (
    AsrEvaluationCase,
    AsrEvaluationDataset,
    AsrGateConfig,
    evaluate_asr_gates,
    load_asr_dataset,
    normalize_asr_text,
    run_asr_evaluation,
    validate_runtime_metadata,
)
from mura.evaluation.asr_live_cli import LiveAudioCase


def test_normalization_is_unicode_and_punctuation_stable() -> None:
    assert normalize_asr_text("  Әлия, ЕРЛАН!  ") == "әлия ерлан"


def test_asr_evaluator_counts_substitution_deletion_and_insertion() -> None:
    dataset = AsrEvaluationDataset(
        dataset_id="unit",
        source_type="synthetic",
        license_or_consent="synthetic",
        cases=[
            AsrEvaluationCase(
                case_id="case",
                language="ru",
                reference="один два три",
                hypothesis="один четыре три пять",
            )
        ],
    )

    report = run_asr_evaluation(dataset)

    assert report.word.substitutions == 1
    assert report.word.insertions == 1
    assert report.word.deletions == 0
    assert report.word.error_rate == 2 / 3


def test_committed_asr_contract_is_non_vacuous_and_passes() -> None:
    report = run_asr_evaluation(load_asr_dataset(Path("benchmarks/asr_contract_v1.json")))
    gate = evaluate_asr_gates(
        report,
        AsrGateConfig.model_validate_json(
            Path("benchmarks/asr_release_gates.json").read_text(encoding="utf-8")
        ),
    )

    assert report.case_count == 12
    assert report.word.substitutions > 0
    assert report.word.deletions > 0
    assert report.word.insertions > 0
    assert report.boundary_cases >= 5
    assert report.repeat_phrases_total >= 2
    assert gate.passed, gate.failures


def test_live_runtime_metadata_fails_closed_without_artifact_hashes() -> None:
    failures = validate_runtime_metadata(
        {
            "model_id": "ai-sage/GigaAM-Multilingual",
            "model_variant": "large_ctc",
            "model_commit": "ac7c6db08133f83478451a659f8470ee8ab47a2d",
            "chunker_version": "silero-smart-v2-exact-overlap",
            "vad_version": "6.2.1",
        }
    )

    assert failures == ["runtime metadata must include at least one artifact SHA-256"]


def test_live_runtime_metadata_accepts_complete_immutable_identity() -> None:
    assert (
        validate_runtime_metadata(
            {
                "model_id": "ai-sage/GigaAM-Multilingual",
                "model_variant": "large_ctc",
                "model_commit": "ac7c6db08133f83478451a659f8470ee8ab47a2d",
                "chunker_version": "silero-smart-v2-exact-overlap",
                "vad_version": "6.2.1",
                "artifact_sha256:model.safetensors": "b" * 64,
            }
        )
        == []
    )


def test_live_runtime_metadata_rejects_model_drift() -> None:
    failures = validate_runtime_metadata(
        {
            "model_id": "ai-sage/GigaAM-Multilingual",
            "model_variant": "large_ctc",
            "model_commit": "a" * 40,
            "chunker_version": "silero-smart-v2-exact-overlap",
            "vad_version": "6.2.1",
            "artifact_sha256:model.safetensors": "b" * 64,
        }
    )

    assert "runtime metadata model_commit does not match the release manifest" in failures


def test_live_manifest_audio_path_must_stay_below_manifest_directory() -> None:
    with pytest.raises(ValidationError, match="manifest directory"):
        LiveAudioCase(
            case_id="case",
            language="ru",
            audio_path=Path("../private.wav"),
            reference="текст",
        )
