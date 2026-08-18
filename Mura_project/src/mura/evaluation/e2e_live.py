from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from mura.domain.models import (
    KnownPerson,
    PipelineRequest,
    PipelineResult,
    StrictModel,
    TranscriptEnvelope,
)
from mura.evaluation.asr import (
    AsrEvaluationCase,
    AsrEvaluationDataset,
    AsrEvaluationReport,
    run_asr_evaluation,
    validate_runtime_metadata,
)
from mura.evaluation.models import (
    BenchmarkCase,
    BenchmarkGold,
    BenchmarkReport,
    DatasetSplit,
    LanguageBucket,
)
from mura.evaluation.scoring import aggregate_case_metrics, score_case
from mura.evidence_recovery import EvidenceOffsetRecoveryMetrics
from mura.pipeline import MuraPipeline
from mura.versioning import get_pipeline_versions

_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class _Transcriber(Protocol):
    def transcribe(
        self,
        *,
        input_path: Path,
        work_dir: Path,
        recording_id: str,
        max_audio_seconds: float | None = None,
    ) -> TranscriptEnvelope: ...


class LiveE2ECase(StrictModel):
    case_id: str = Field(min_length=1)
    language: Literal["ru", "kk", "mixed"]
    audio_path: Path
    reference_text: str = Field(min_length=1)
    speaker_id: str = Field(min_length=1)
    speaker_name: str = Field(min_length=1)
    known_people: list[KnownPerson] = Field(default_factory=list)
    gold: BenchmarkGold

    @model_validator(mode="after")
    def validate_local_relative_path(self) -> LiveE2ECase:
        if self.audio_path.is_absolute() or ".." in self.audio_path.parts:
            raise ValueError("audio_path must stay inside the manifest directory")
        return self


class LiveE2EManifest(StrictModel):
    schema_version: str = "e2e-live-manifest-v1"
    dataset_id: str = Field(min_length=1)
    source_type: Literal["public_licensed", "approved_private"]
    license_or_consent: str = Field(min_length=1, max_length=256)
    cases: list[LiveE2ECase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> LiveE2EManifest:
        if "\n" in self.license_or_consent or "\r" in self.license_or_consent:
            raise ValueError("license_or_consent must be a non-sensitive single-line record ID")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("live E2E case IDs must be unique")
        return self


class LiveE2ECaseRuntime(StrictModel):
    case_id: str
    pipeline_seconds: float = Field(ge=0)
    asr_seconds: float = Field(ge=0)
    cleaner_fallback_used: bool
    focused_partial_failures: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    provider_models: list[str] = Field(default_factory=list)


class LiveE2EReport(StrictModel):
    report_schema_version: str = "e2e-live-report-v1"
    dataset_id: str
    source_type: str
    license_or_consent: str
    pipeline_versions: dict[str, str]
    asr: AsrEvaluationReport
    ml: BenchmarkReport
    runtimes: list[LiveE2ECaseRuntime]
    runtime_metadata_failures: list[str] = Field(default_factory=list)
    source_commit: str = "unknown"


class LiveE2EGateConfig(StrictModel):
    schema_version: str = "e2e-live-release-gates-v1"
    minimum_case_count: int = Field(ge=1)
    minimum_language_case_count: dict[str, int]
    maximum_word_error_rate: float = Field(ge=0)
    maximum_character_error_rate: float = Field(ge=0)
    minimum_person_f1: float = Field(ge=0, le=1)
    minimum_relationship_precision: float = Field(ge=0, le=1)
    minimum_relationship_recall: float = Field(ge=0, le=1)
    minimum_provenance_completeness: float = Field(ge=0, le=1)
    maximum_unsafe_verification_statuses: int = Field(ge=0)
    maximum_unsafe_story_privacy: int = Field(ge=0)
    maximum_fatal_contract_failures: int = Field(ge=0)
    maximum_model_calls_per_case: int = Field(ge=1)
    maximum_pipeline_seconds_per_case: float = Field(gt=0)
    maximum_asr_seconds_per_case: float = Field(gt=0)
    require_source_commit_sha: bool = True
    maximum_missing_provider_model_cases: int = Field(default=0, ge=0)
    maximum_pipeline_version_mismatches: int = Field(default=0, ge=0)
    maximum_case_id_mismatches: int = Field(default=0, ge=0)


class LiveE2EGateResult(StrictModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)
    measurements: dict[str, int | float] = Field(default_factory=dict)


def load_live_e2e_manifest(path: Path) -> LiveE2EManifest:
    return LiveE2EManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_live_e2e_gate_config(path: Path) -> LiveE2EGateConfig:
    return LiveE2EGateConfig.model_validate_json(path.read_text(encoding="utf-8"))


def _evidence_metrics(processing: dict[str, Any]) -> EvidenceOffsetRecoveryMetrics:
    extractor = processing.get("extractor_usage", {})
    raw = extractor.get("evidence_offset_recovery", {}) if isinstance(extractor, dict) else {}
    return EvidenceOffsetRecoveryMetrics(
        already_valid=int(raw.get("already_valid", 0) or 0),
        recovered=int(raw.get("recovered", 0) or 0),
        ambiguous=int(raw.get("ambiguous", 0) or 0),
        missing=int(raw.get("missing", 0) or 0),
        wrong_source_layer=int(raw.get("wrong_source_layer", 0) or 0),
        unknown_segment=int(raw.get("unknown_segment", 0) or 0),
        invalid_text=int(raw.get("invalid_text", 0) or 0),
        unrecoverable=int(raw.get("unrecoverable", 0) or 0),
    )


def _issues(processing: dict[str, Any]) -> list[dict[str, Any]]:
    extractor = processing.get("extractor_usage", {})
    if not isinstance(extractor, dict):
        return []
    value = extractor.get("extraction_issues", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _runtime(case_id: str, result: PipelineResult) -> LiveE2ECaseRuntime:
    cleaner = result.processing.get("cleaner_usage", {})
    extractor = result.processing.get("extractor_usage", {})
    passes = extractor.get("focused_passes", []) if isinstance(extractor, dict) else []
    cleaner_repair_calls = int(
        isinstance(cleaner, dict) and bool(cleaner.get("repair_attempted", False))
    )
    model_calls = (
        1
        + cleaner_repair_calls
        + sum(int(item.get("request_count", 0) or 0) for item in passes if isinstance(item, dict))
    )
    provider_models = sorted(
        {
            str(value)
            for value in (
                cleaner.get("model") if isinstance(cleaner, dict) else None,
                extractor.get("model") if isinstance(extractor, dict) else None,
            )
            if isinstance(value, str) and value
        }
    )
    return LiveE2ECaseRuntime(
        case_id=case_id,
        pipeline_seconds=float(result.processing.get("total_seconds", 0.0) or 0.0),
        asr_seconds=float(result.transcript.processing_seconds or 0.0),
        cleaner_fallback_used=bool(
            isinstance(cleaner, dict) and cleaner.get("fallback_used", False)
        ),
        focused_partial_failures=int(
            extractor.get("focused_partial_failures", 0) if isinstance(extractor, dict) else 0
        ),
        model_calls=model_calls,
        prompt_tokens=int(extractor.get("prompt_tokens", 0) or 0)
        + int(cleaner.get("prompt_tokens", 0) or 0),
        completion_tokens=int(extractor.get("completion_tokens", 0) or 0)
        + int(cleaner.get("completion_tokens", 0) or 0),
        total_tokens=int(extractor.get("total_tokens", 0) or 0)
        + int(cleaner.get("total_tokens", 0) or 0),
        provider_models=provider_models,
    )


def run_live_e2e(
    *,
    manifest_path: Path,
    transcriber: _Transcriber,
    pipeline: MuraPipeline,
    max_audio_seconds: float,
    source_commit: str = "unknown",
) -> LiveE2EReport:
    manifest_path = manifest_path.resolve()
    manifest = load_live_e2e_manifest(manifest_path)
    asr_cases: list[AsrEvaluationCase] = []
    scored = []
    runtimes: list[LiveE2ECaseRuntime] = []
    runtime_metadata: dict[str, str | int | float | bool] = {}
    metadata_consistency_failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="mura-live-e2e-") as directory:
        work_root = Path(directory)
        for index, case in enumerate(manifest.cases, start=1):
            audio_path = (manifest_path.parent / case.audio_path).resolve()
            if manifest_path.parent not in audio_path.parents or not audio_path.is_file():
                raise FileNotFoundError(case.audio_path)
            transcript = transcriber.transcribe(
                input_path=audio_path,
                work_dir=work_root / f"case-{index:03d}",
                recording_id=case.case_id,
                max_audio_seconds=max_audio_seconds,
            )
            case_metadata = dict(transcript.asr_metadata)
            if not runtime_metadata:
                runtime_metadata = case_metadata
            else:
                for key in sorted(set(runtime_metadata) | set(case_metadata)):
                    if runtime_metadata.get(key) != case_metadata.get(key):
                        metadata_consistency_failures.append(
                            f"runtime metadata differs across cases: {key}"
                        )
            result = pipeline.process(
                PipelineRequest(
                    transcript=transcript,
                    speaker_id=case.speaker_id,
                    speaker_name=case.speaker_name,
                    known_people=case.known_people,
                )
            )
            benchmark_case = BenchmarkCase(
                case_id=case.case_id,
                title=case.case_id,
                language=LanguageBucket(case.language),
                construction_tags=["live_e2e"],
                speaker_id=case.speaker_id,
                speaker_name=case.speaker_name,
                transcript=transcript,
                raw_extraction=result.extraction.model_dump(mode="json"),
                gold=case.gold,
            )
            scored.append(
                score_case(
                    case=benchmark_case,
                    dataset_id=manifest.dataset_id,
                    split=DatasetSplit.TEST,
                    extraction=result.extraction,
                    issues=_issues(result.processing),
                    evidence_closure_relationships=int(
                        result.processing.get("extractor_usage", {}).get(
                            "evidence_closure_relationships", 0
                        )
                    ),
                    evidence_recovery=_evidence_metrics(result.processing),
                )
            )
            runtimes.append(_runtime(case.case_id, result))
            asr_cases.append(
                AsrEvaluationCase(
                    case_id=case.case_id,
                    language=case.language,
                    reference=case.reference_text,
                    hypothesis=transcript.full_text,
                )
            )

    asr_report = run_asr_evaluation(
        AsrEvaluationDataset(
            dataset_id=f"{manifest.dataset_id}-asr",
            source_type=manifest.source_type,
            license_or_consent=manifest.license_or_consent,
            runtime_metadata=runtime_metadata,
            cases=asr_cases,
        )
    )
    ml_report = BenchmarkReport(
        report_schema_version="evaluation-report-v4-live-e2e",
        manifest_path=manifest_path.name,
        pipeline_versions=get_pipeline_versions().model_dump(mode="json"),
        cases=scored,
        summary=aggregate_case_metrics(scored),
    )
    return LiveE2EReport(
        dataset_id=manifest.dataset_id,
        source_type=manifest.source_type,
        license_or_consent=manifest.license_or_consent,
        pipeline_versions=get_pipeline_versions().model_dump(mode="json"),
        asr=asr_report,
        ml=ml_report,
        runtimes=runtimes,
        runtime_metadata_failures=sorted(
            set(
                [
                    *metadata_consistency_failures,
                    *validate_runtime_metadata(runtime_metadata),
                ]
            )
        ),
        source_commit=source_commit,
    )


def evaluate_live_e2e_gates(
    report: LiveE2EReport,
    config: LiveE2EGateConfig,
) -> LiveE2EGateResult:
    summary = report.ml.summary
    languages = Counter(item.language for item in report.asr.cases)
    asr_case_ids = {item.case_id for item in report.asr.cases}
    ml_case_ids = {item.case_id for item in report.ml.cases}
    runtime_case_ids = {item.case_id for item in report.runtimes}
    case_id_mismatches = len(
        (asr_case_ids ^ ml_case_ids)
        | (asr_case_ids ^ runtime_case_ids)
        | (ml_case_ids ^ runtime_case_ids)
    )
    measurements: dict[str, int | float] = {
        "case_count": report.asr.case_count,
        "word_error_rate": report.asr.word.error_rate,
        "character_error_rate": report.asr.character.error_rate,
        "person_f1": summary.person_mentions.f1,
        "relationship_precision": summary.relationships.precision,
        "relationship_recall": summary.relationships.recall,
        "provenance_completeness": summary.provenance_completeness.value,
        "unsafe_verification_statuses": summary.unsafe_verification_statuses,
        "unsafe_story_privacy": summary.unsafe_story_privacy,
        "fatal_contract_failures": summary.fatal_contract_failures,
        "maximum_model_calls": max(item.model_calls for item in report.runtimes),
        "maximum_pipeline_seconds": max(item.pipeline_seconds for item in report.runtimes),
        "maximum_asr_seconds": max(item.asr_seconds for item in report.runtimes),
        "runtime_metadata_failures": len(report.runtime_metadata_failures),
        "source_commit_invalid": int(not bool(_COMMIT_SHA_PATTERN.fullmatch(report.source_commit))),
        "missing_provider_model_cases": sum(not item.provider_models for item in report.runtimes),
        "case_id_mismatches": case_id_mismatches,
        "pipeline_version_mismatches": int(
            report.pipeline_versions != get_pipeline_versions().model_dump(mode="json")
            or report.ml.pipeline_versions != report.pipeline_versions
        ),
    }
    failures = list(report.runtime_metadata_failures)

    def minimum(name: str, threshold: int | float) -> None:
        if measurements[name] < threshold:
            failures.append(f"{name}={measurements[name]} is below minimum {threshold}")

    def maximum(name: str, threshold: int | float) -> None:
        if measurements[name] > threshold:
            failures.append(f"{name}={measurements[name]} exceeds maximum {threshold}")

    minimum("case_count", config.minimum_case_count)
    for language, threshold in config.minimum_language_case_count.items():
        actual = languages.get(language, 0)
        measurements[f"language_{language}_case_count"] = actual
        if actual < threshold:
            failures.append(f"language {language} case count {actual} < {threshold}")
    maximum("word_error_rate", config.maximum_word_error_rate)
    maximum("character_error_rate", config.maximum_character_error_rate)
    minimum("person_f1", config.minimum_person_f1)
    minimum("relationship_precision", config.minimum_relationship_precision)
    minimum("relationship_recall", config.minimum_relationship_recall)
    minimum("provenance_completeness", config.minimum_provenance_completeness)
    maximum("unsafe_verification_statuses", config.maximum_unsafe_verification_statuses)
    maximum("unsafe_story_privacy", config.maximum_unsafe_story_privacy)
    maximum("fatal_contract_failures", config.maximum_fatal_contract_failures)
    maximum("maximum_model_calls", config.maximum_model_calls_per_case)
    maximum("maximum_pipeline_seconds", config.maximum_pipeline_seconds_per_case)
    maximum("maximum_asr_seconds", config.maximum_asr_seconds_per_case)
    maximum("runtime_metadata_failures", 0)
    if config.require_source_commit_sha:
        maximum("source_commit_invalid", 0)
    maximum(
        "missing_provider_model_cases",
        config.maximum_missing_provider_model_cases,
    )
    maximum(
        "pipeline_version_mismatches",
        config.maximum_pipeline_version_mismatches,
    )
    maximum("case_id_mismatches", config.maximum_case_id_mismatches)
    return LiveE2EGateResult(passed=not failures, failures=failures, measurements=measurements)


def render_live_e2e_report(report: LiveE2EReport, gate: LiveE2EGateResult) -> str:
    lines = [
        "# Mura Live End-to-End ML Evaluation",
        "",
        f"- Dataset: `{report.dataset_id}`",
        f"- Source type: `{report.source_type}`",
        f"- License/consent: {report.license_or_consent}",
        f"- Source commit: `{report.source_commit}`",
        "",
    ]
    for name, value in sorted(gate.measurements.items()):
        lines.append(f"- {name}: `{value}`")
    lines.extend(["", f"## Gate: {'PASS' if gate.passed else 'FAIL'}"])
    lines.extend(f"- {failure}" for failure in gate.failures)
    return "\n".join(lines)


def write_live_e2e_json(report: LiveE2EReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
