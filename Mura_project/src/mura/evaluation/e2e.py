from __future__ import annotations

import hashlib
import json
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from mura.deepseek.anchor_prompts import (
    FOCUSED_CORE_EXTRACTOR_SYSTEM_PROMPT,
    FOCUSED_CORE_REPAIR_SYSTEM_PROMPT,
    FOCUSED_EVENT_EXTRACTOR_SYSTEM_PROMPT,
    FOCUSED_EVENT_REPAIR_SYSTEM_PROMPT,
    FOCUSED_STORY_EXTRACTOR_SYSTEM_PROMPT,
    FOCUSED_STORY_REPAIR_SYSTEM_PROMPT,
)
from mura.deepseek.client import DeepSeekError, DeepSeekUsage
from mura.deepseek.prompts import CLEANER_REPAIR_SYSTEM_PROMPT, CLEANER_SYSTEM_PROMPT
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import (
    EvidenceBackedObject,
    PipelineRequest,
    PipelineResult,
    ResolutionStatus,
    StrictModel,
    VerificationStatus,
)
from mura.evaluation.asr import (
    AsrEvaluationCase,
    AsrEvaluationDataset,
    AsrEvaluationReport,
    run_asr_evaluation,
)
from mura.evaluation.models import LanguageBucket, RatioMetric
from mura.pipeline import MuraPipeline
from mura.validation import ContractValidationError, validate_extraction_result
from mura.versioning import get_pipeline_versions


class FrozenProviderStage(StrEnum):
    CLEANER = "cleaner"
    CLEANER_REPAIR = "cleaner_repair"
    CORE = "core"
    CORE_REPAIR = "core_repair"
    EVENTS = "events"
    EVENTS_REPAIR = "events_repair"
    STORIES = "stories"
    STORIES_REPAIR = "stories_repair"


_PROMPT_STAGE = {
    CLEANER_SYSTEM_PROMPT: FrozenProviderStage.CLEANER,
    CLEANER_REPAIR_SYSTEM_PROMPT: FrozenProviderStage.CLEANER_REPAIR,
    FOCUSED_CORE_EXTRACTOR_SYSTEM_PROMPT: FrozenProviderStage.CORE,
    FOCUSED_CORE_REPAIR_SYSTEM_PROMPT: FrozenProviderStage.CORE_REPAIR,
    FOCUSED_EVENT_EXTRACTOR_SYSTEM_PROMPT: FrozenProviderStage.EVENTS,
    FOCUSED_EVENT_REPAIR_SYSTEM_PROMPT: FrozenProviderStage.EVENTS_REPAIR,
    FOCUSED_STORY_EXTRACTOR_SYSTEM_PROMPT: FrozenProviderStage.STORIES,
    FOCUSED_STORY_REPAIR_SYSTEM_PROMPT: FrozenProviderStage.STORIES_REPAIR,
}


class FrozenProviderResponse(StrictModel):
    stage: Literal[
        "cleaner",
        "cleaner_repair",
        "core",
        "core_repair",
        "events",
        "events_repair",
        "stories",
        "stories_repair",
    ]
    response: dict[str, Any] | None = None
    error: Literal["provider_error", "timeout"] | None = None
    model: str = "frozen-deepseek-fixture"
    prompt_tokens: int = Field(default=100, ge=0)
    completion_tokens: int = Field(default=50, ge=0)
    request_seconds: float = Field(default=0.1, ge=0)

    @model_validator(mode="after")
    def validate_outcome(self) -> FrozenProviderResponse:
        if (self.response is None) == (self.error is None):
            raise ValueError("frozen provider response requires exactly one of response or error")
        return self


class E2EExpected(StrictModel):
    people_ids: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    description_ids: list[str] = Field(default_factory=list)
    story_ids: list[str] = Field(default_factory=list)
    question_ids: list[str] = Field(default_factory=list)
    resolution_statuses: dict[str, ResolutionStatus] = Field(default_factory=dict)
    resolution_person_ids: dict[str, str] = Field(default_factory=dict)
    required_issue_codes: list[str] = Field(default_factory=list)
    cleaner_fallback_used: bool = False
    minimum_extractor_repairs: int = Field(default=0, ge=0)
    minimum_partial_failures: int = Field(default=0, ge=0)
    maximum_model_calls: int = Field(default=6, ge=1, le=12)


class E2ECase(StrictModel):
    case_id: str = Field(min_length=1)
    language: LanguageBucket
    construction_tags: list[str] = Field(default_factory=list)
    reference_text: str = Field(min_length=1)
    request: PipelineRequest
    provider_responses: list[FrozenProviderResponse] = Field(min_length=1)
    expected: E2EExpected

    @model_validator(mode="after")
    def validate_identity(self) -> E2ECase:
        if self.request.transcript.recording_id != self.case_id:
            raise ValueError("E2E case_id must equal transcript recording_id")
        return self


class E2EDataset(StrictModel):
    schema_version: str = "e2e-evaluation-dataset-v1"
    dataset_id: str = Field(min_length=1)
    source_type: Literal["synthetic", "public_licensed", "approved_private"]
    license_or_consent: str = Field(min_length=1)
    description: str = ""
    external_stages_frozen: bool = True
    cases: list[E2ECase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> E2EDataset:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("E2E case IDs must be unique")
        if not self.external_stages_frozen:
            raise ValueError("offline E2E datasets must declare frozen external stages")
        return self


class E2ECaseReport(StrictModel):
    case_id: str
    language: LanguageBucket
    construction_tags: list[str]
    passed: bool
    failures: list[str] = Field(default_factory=list)
    provider_stages: list[str] = Field(default_factory=list)
    model_calls: int = Field(ge=0)
    unconsumed_provider_responses: int = Field(ge=0)
    deterministic_replay: bool
    output_digest: str = Field(min_length=64, max_length=64)
    expected_objects: int = Field(ge=0)
    matched_objects: int = Field(ge=0)
    provenance_objects: int = Field(ge=0)
    provenance_complete_objects: int = Field(ge=0)
    unsafe_verification_statuses: int = Field(ge=0)
    unsafe_story_privacy: int = Field(ge=0)
    cleaner_fallback_used: bool
    extractor_repairs: int = Field(ge=0)
    focused_partial_failures: int = Field(ge=0)
    review_resolutions: int = Field(ge=0)
    issue_codes: list[str] = Field(default_factory=list)
    pipeline_versions_complete: bool


class E2ESummary(StrictModel):
    case_count: int = Field(ge=1)
    language_case_count: dict[str, int]
    passed_cases: int = Field(ge=0)
    case_pass_rate: float = Field(ge=0, le=1)
    deterministic_replay: RatioMetric
    semantic_accuracy: RatioMetric
    provenance_completeness: RatioMetric
    unsafe_verification_statuses: int = Field(ge=0)
    unsafe_story_privacy: int = Field(ge=0)
    unexpected_or_unconsumed_provider_responses: int = Field(ge=0)
    maximum_model_calls_observed: int = Field(ge=0)
    cleaner_fallback_cases: int = Field(ge=0)
    extractor_repair_cases: int = Field(ge=0)
    focused_partial_failure_cases: int = Field(ge=0)
    review_resolution_cases: int = Field(ge=0)
    pipeline_version_failures: int = Field(ge=0)
    fatal_case_failures: int = Field(ge=0)


class E2EReport(StrictModel):
    report_schema_version: str = "e2e-evaluation-report-v1"
    dataset_id: str
    source_type: str
    license_or_consent: str
    external_stages_frozen: bool
    pipeline_versions: dict[str, str]
    asr: AsrEvaluationReport
    cases: list[E2ECaseReport]
    summary: E2ESummary


class E2EGateConfig(StrictModel):
    schema_version: str = "e2e-release-gates-v1"
    minimum_case_count: int = Field(ge=1)
    minimum_language_case_count: dict[str, int]
    minimum_case_pass_rate: float = Field(ge=0, le=1)
    minimum_deterministic_replay: float = Field(ge=0, le=1)
    minimum_semantic_accuracy: float = Field(ge=0, le=1)
    minimum_provenance_completeness: float = Field(ge=0, le=1)
    maximum_unsafe_verification_statuses: int = Field(ge=0)
    maximum_unsafe_story_privacy: int = Field(ge=0)
    maximum_unexpected_or_unconsumed_provider_responses: int = Field(ge=0)
    maximum_model_calls_per_case: int = Field(ge=1)
    minimum_cleaner_fallback_cases: int = Field(ge=0)
    minimum_extractor_repair_cases: int = Field(ge=0)
    minimum_focused_partial_failure_cases: int = Field(ge=0)
    minimum_review_resolution_cases: int = Field(ge=0)
    maximum_pipeline_version_failures: int = Field(ge=0)
    maximum_fatal_case_failures: int = Field(ge=0)
    maximum_word_error_rate: float = Field(ge=0)
    maximum_character_error_rate: float = Field(ge=0)


class E2EGateResult(StrictModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)
    measurements: dict[str, int | float] = Field(default_factory=dict)


class _FrozenDeepSeekClient:
    def __init__(self, responses: list[FrozenProviderResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []
        self.unexpected_calls = 0

    @property
    def remaining(self) -> int:
        return len(self._responses)

    def request_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        max_tokens: int,
        attempts: int = 3,
    ) -> tuple[dict[str, Any], DeepSeekUsage]:
        del payload, max_tokens, attempts
        actual_stage = _PROMPT_STAGE.get(system_prompt)
        if actual_stage is None:
            self.unexpected_calls += 1
            raise DeepSeekError("offline E2E fixture received an unknown prompt")
        self.calls.append(actual_stage)
        if not self._responses:
            self.unexpected_calls += 1
            raise DeepSeekError("offline E2E fixture exhausted provider responses")
        expected = self._responses.pop(0)
        if expected.stage != actual_stage:
            self.unexpected_calls += 1
            raise DeepSeekError(
                f"offline E2E stage mismatch: expected {expected.stage}, got {actual_stage}"
            )
        if expected.error is not None:
            if expected.error == "timeout":
                raise DeepSeekError("frozen provider timeout")
            raise DeepSeekError("frozen provider error")
        assert expected.response is not None
        return expected.response, DeepSeekUsage(
            model=expected.model,
            finish_reason="stop",
            request_seconds=expected.request_seconds,
            prompt_tokens=expected.prompt_tokens,
            completion_tokens=expected.completion_tokens,
            total_tokens=expected.prompt_tokens + expected.completion_tokens,
        )


def load_e2e_dataset(path: Path) -> E2EDataset:
    return E2EDataset.model_validate_json(path.read_text(encoding="utf-8"))


def load_e2e_gate_config(path: Path) -> E2EGateConfig:
    return E2EGateConfig.model_validate_json(path.read_text(encoding="utf-8"))


def _all_objects(result: PipelineResult) -> list[EvidenceBackedObject]:
    extraction = result.extraction
    return [
        *extraction.people_mentions,
        *extraction.relationship_claims,
        *extraction.events,
        *extraction.descriptions,
        *extraction.stories,
        *extraction.unresolved_questions,
    ]


def _canonical_digest(result: PipelineResult) -> str:
    payload = result.model_dump(mode="json")
    processing = payload.get("processing")
    if isinstance(processing, dict):
        processing.pop("total_seconds", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _issue_codes(result: PipelineResult) -> list[str]:
    usage = result.processing.get("extractor_usage", {})
    codes: list[str] = []
    if isinstance(usage, dict):
        for issue in usage.get("extraction_issues", []):
            if isinstance(issue, dict) and isinstance(issue.get("code"), str):
                codes.append(issue["code"])
        for pass_report in usage.get("focused_passes", []):
            if not isinstance(pass_report, dict):
                continue
            for issue in pass_report.get("issues", []):
                if isinstance(issue, dict) and isinstance(issue.get("code"), str):
                    codes.append(issue["code"])
    return sorted(set(codes))


def _actual_ids(result: PipelineResult) -> dict[str, set[str]]:
    extraction = result.extraction
    return {
        "people": {item.mention_id for item in extraction.people_mentions},
        "relationships": {item.relationship_id for item in extraction.relationship_claims},
        "events": {item.event_id for item in extraction.events},
        "descriptions": {item.description_id for item in extraction.descriptions},
        "stories": {item.story_id for item in extraction.stories},
        "questions": {item.question_id for item in extraction.unresolved_questions},
    }


def _expected_ids(expected: E2EExpected) -> dict[str, set[str]]:
    return {
        "people": set(expected.people_ids),
        "relationships": set(expected.relationship_ids),
        "events": set(expected.event_ids),
        "descriptions": set(expected.description_ids),
        "stories": set(expected.story_ids),
        "questions": set(expected.question_ids),
    }


def _run_once(case: E2ECase) -> tuple[PipelineResult, _FrozenDeepSeekClient]:
    client = _FrozenDeepSeekClient(case.provider_responses)
    pipeline = MuraPipeline(
        DeepSeekPipelineService(client, focused_extraction=True)  # type: ignore[arg-type]
    )
    result = pipeline.process(case.request)
    return result, client


def _evaluate_case(case: E2ECase) -> E2ECaseReport:
    failures: list[str] = []
    try:
        first, first_client = _run_once(case)
        second, second_client = _run_once(case)
    except (DeepSeekError, ContractValidationError, ValueError) as exc:
        return E2ECaseReport(
            case_id=case.case_id,
            language=case.language,
            construction_tags=case.construction_tags,
            passed=False,
            failures=[f"fatal_pipeline_failure:{type(exc).__name__}"],
            provider_stages=[],
            model_calls=0,
            unconsumed_provider_responses=len(case.provider_responses),
            deterministic_replay=False,
            output_digest="0" * 64,
            expected_objects=sum(len(value) for value in _expected_ids(case.expected).values()),
            matched_objects=0,
            provenance_objects=0,
            provenance_complete_objects=0,
            unsafe_verification_statuses=0,
            unsafe_story_privacy=0,
            cleaner_fallback_used=False,
            extractor_repairs=0,
            focused_partial_failures=0,
            review_resolutions=0,
            issue_codes=[],
            pipeline_versions_complete=False,
        )

    digest = _canonical_digest(first)
    deterministic = digest == _canonical_digest(second)
    if not deterministic:
        failures.append("nondeterministic_replay")
    try:
        validate_extraction_result(
            first.transcript,
            first.extraction,
            cleaned=first.cleaned_transcript,
        )
    except ContractValidationError:
        failures.append("extraction_contract_invalid")

    expected_ids = _expected_ids(case.expected)
    actual_ids = _actual_ids(first)
    expected_objects = sum(len(value) for value in expected_ids.values())
    matched_objects = sum(
        len(actual_ids[key].intersection(value)) for key, value in expected_ids.items()
    )
    for object_type, expected in expected_ids.items():
        if actual_ids[object_type] != expected:
            failures.append(f"{object_type}_mismatch")

    resolution_by_id = {item.mention_id: item for item in first.resolutions}
    for mention_id, expected_status in case.expected.resolution_statuses.items():
        actual = resolution_by_id.get(mention_id)
        if actual is None or actual.status is not expected_status:
            failures.append(f"resolution_status_mismatch:{mention_id}")
    for mention_id, expected_person_id in case.expected.resolution_person_ids.items():
        actual = resolution_by_id.get(mention_id)
        if actual is None or actual.person_id != expected_person_id:
            failures.append(f"resolution_person_mismatch:{mention_id}")

    objects = _all_objects(first)
    evidence_ids = {item.evidence_id for item in first.extraction.evidence_spans}
    provenance_complete = sum(
        item.provenance is not None
        and bool(item.evidence_ids)
        and not (set(item.evidence_ids) - evidence_ids)
        for item in objects
    )
    unsafe_statuses = sum(
        getattr(item, "verification_status", VerificationStatus.UNREVIEWED)
        is not VerificationStatus.UNREVIEWED
        for item in objects
    )
    unsafe_statuses += sum(
        item.verification_status is not VerificationStatus.UNREVIEWED
        for item in first.extraction.coreference_links
    )
    unsafe_statuses += sum(
        item.verification_status is not VerificationStatus.UNREVIEWED
        for item in first.extraction.conflict_sets
    )
    unsafe_privacy = sum(item.privacy.value != "private" for item in first.extraction.stories)
    if unsafe_statuses:
        failures.append("unsafe_verification_status")
    if unsafe_privacy:
        failures.append("unsafe_story_privacy")

    issue_codes = _issue_codes(first)
    missing_issue_codes = set(case.expected.required_issue_codes) - set(issue_codes)
    if missing_issue_codes:
        failures.append("missing_required_issue_codes")

    cleaner_usage = first.processing.get("cleaner_usage", {})
    extractor_usage = first.processing.get("extractor_usage", {})
    cleaner_fallback = bool(
        isinstance(cleaner_usage, dict) and cleaner_usage.get("fallback_used", False)
    )
    if cleaner_fallback != case.expected.cleaner_fallback_used:
        failures.append("cleaner_fallback_mismatch")
    extractor_repairs = 0
    partial_failures = 0
    if isinstance(extractor_usage, dict):
        extractor_repairs = int(extractor_usage.get("focused_repair_calls", 0) or 0)
        partial_failures = int(extractor_usage.get("focused_partial_failures", 0) or 0)
    if extractor_repairs < case.expected.minimum_extractor_repairs:
        failures.append("extractor_repair_count_below_expected")
    if partial_failures < case.expected.minimum_partial_failures:
        failures.append("partial_failure_count_below_expected")

    model_calls = len(first_client.calls)
    if model_calls > case.expected.maximum_model_calls:
        failures.append("model_call_budget_exceeded")
    unconsumed = first_client.remaining + second_client.remaining
    unexpected = first_client.unexpected_calls + second_client.unexpected_calls
    if unconsumed or unexpected:
        failures.append("provider_sequence_not_fully_consumed")

    current_versions = get_pipeline_versions().model_dump(mode="json")
    persisted_versions = first.processing.get("versions")
    versions_complete = persisted_versions == current_versions and all(current_versions.values())
    if not versions_complete:
        failures.append("pipeline_versions_incomplete")

    review_resolutions = sum(
        item.status is ResolutionStatus.NEEDS_REVIEW for item in first.resolutions
    )
    return E2ECaseReport(
        case_id=case.case_id,
        language=case.language,
        construction_tags=case.construction_tags,
        passed=not failures,
        failures=failures,
        provider_stages=first_client.calls,
        model_calls=model_calls,
        unconsumed_provider_responses=unconsumed + unexpected,
        deterministic_replay=deterministic,
        output_digest=digest,
        expected_objects=expected_objects,
        matched_objects=matched_objects,
        provenance_objects=len(objects),
        provenance_complete_objects=provenance_complete,
        unsafe_verification_statuses=unsafe_statuses,
        unsafe_story_privacy=unsafe_privacy,
        cleaner_fallback_used=cleaner_fallback,
        extractor_repairs=extractor_repairs,
        focused_partial_failures=partial_failures,
        review_resolutions=review_resolutions,
        issue_codes=issue_codes,
        pipeline_versions_complete=versions_complete,
    )


def _ratio(numerator: int, denominator: int) -> RatioMetric:
    return RatioMetric(
        numerator=numerator,
        denominator=denominator,
        value=round(numerator / denominator, 6) if denominator else 1.0,
    )


def run_e2e_evaluation(dataset: E2EDataset) -> E2EReport:
    cases = [_evaluate_case(case) for case in dataset.cases]
    language_counts = Counter(case.language.value for case in cases)
    asr = run_asr_evaluation(
        AsrEvaluationDataset(
            dataset_id=f"{dataset.dataset_id}-frozen-asr",
            source_type=dataset.source_type,
            license_or_consent=dataset.license_or_consent,
            description=(
                "Frozen ASR hypotheses embedded in offline E2E fixtures. "
                "This does not measure live model quality."
            ),
            cases=[
                AsrEvaluationCase(
                    case_id=case.case_id,
                    language=case.language.value,  # type: ignore[arg-type]
                    reference=case.reference_text,
                    hypothesis=case.request.transcript.full_text,
                )
                for case in dataset.cases
            ],
        )
    )
    expected_objects = sum(case.expected_objects for case in cases)
    matched_objects = sum(case.matched_objects for case in cases)
    provenance_objects = sum(case.provenance_objects for case in cases)
    provenance_complete = sum(case.provenance_complete_objects for case in cases)
    summary = E2ESummary(
        case_count=len(cases),
        language_case_count=dict(sorted(language_counts.items())),
        passed_cases=sum(case.passed for case in cases),
        case_pass_rate=sum(case.passed for case in cases) / len(cases),
        deterministic_replay=_ratio(sum(case.deterministic_replay for case in cases), len(cases)),
        semantic_accuracy=_ratio(matched_objects, expected_objects),
        provenance_completeness=_ratio(provenance_complete, provenance_objects),
        unsafe_verification_statuses=sum(case.unsafe_verification_statuses for case in cases),
        unsafe_story_privacy=sum(case.unsafe_story_privacy for case in cases),
        unexpected_or_unconsumed_provider_responses=sum(
            case.unconsumed_provider_responses for case in cases
        ),
        maximum_model_calls_observed=max(case.model_calls for case in cases),
        cleaner_fallback_cases=sum(case.cleaner_fallback_used for case in cases),
        extractor_repair_cases=sum(case.extractor_repairs > 0 for case in cases),
        focused_partial_failure_cases=sum(case.focused_partial_failures > 0 for case in cases),
        review_resolution_cases=sum(case.review_resolutions > 0 for case in cases),
        pipeline_version_failures=sum(not case.pipeline_versions_complete for case in cases),
        fatal_case_failures=sum(
            any(item.startswith("fatal_pipeline_failure") for item in case.failures)
            for case in cases
        ),
    )
    return E2EReport(
        dataset_id=dataset.dataset_id,
        source_type=dataset.source_type,
        license_or_consent=dataset.license_or_consent,
        external_stages_frozen=dataset.external_stages_frozen,
        pipeline_versions=get_pipeline_versions().model_dump(mode="json"),
        asr=asr,
        cases=cases,
        summary=summary,
    )


def evaluate_e2e_gates(report: E2EReport, config: E2EGateConfig) -> E2EGateResult:
    summary = report.summary
    measurements: dict[str, int | float] = {
        "case_count": summary.case_count,
        "case_pass_rate": summary.case_pass_rate,
        "deterministic_replay": summary.deterministic_replay.value,
        "semantic_accuracy": summary.semantic_accuracy.value,
        "provenance_completeness": summary.provenance_completeness.value,
        "unsafe_verification_statuses": summary.unsafe_verification_statuses,
        "unsafe_story_privacy": summary.unsafe_story_privacy,
        "unexpected_or_unconsumed_provider_responses": (
            summary.unexpected_or_unconsumed_provider_responses
        ),
        "maximum_model_calls_observed": summary.maximum_model_calls_observed,
        "cleaner_fallback_cases": summary.cleaner_fallback_cases,
        "extractor_repair_cases": summary.extractor_repair_cases,
        "focused_partial_failure_cases": summary.focused_partial_failure_cases,
        "review_resolution_cases": summary.review_resolution_cases,
        "pipeline_version_failures": summary.pipeline_version_failures,
        "fatal_case_failures": summary.fatal_case_failures,
        "word_error_rate": report.asr.word.error_rate,
        "character_error_rate": report.asr.character.error_rate,
    }
    failures: list[str] = []

    def minimum(name: str, threshold: int | float) -> None:
        if measurements[name] < threshold:
            failures.append(f"{name}={measurements[name]} is below minimum {threshold}")

    def maximum(name: str, threshold: int | float) -> None:
        if measurements[name] > threshold:
            failures.append(f"{name}={measurements[name]} exceeds maximum {threshold}")

    minimum("case_count", config.minimum_case_count)
    for language, threshold in config.minimum_language_case_count.items():
        actual = summary.language_case_count.get(language, 0)
        measurements[f"language_{language}_case_count"] = actual
        if actual < threshold:
            failures.append(f"language {language} case count {actual} < {threshold}")
    minimum("case_pass_rate", config.minimum_case_pass_rate)
    minimum("deterministic_replay", config.minimum_deterministic_replay)
    minimum("semantic_accuracy", config.minimum_semantic_accuracy)
    minimum("provenance_completeness", config.minimum_provenance_completeness)
    maximum("unsafe_verification_statuses", config.maximum_unsafe_verification_statuses)
    maximum("unsafe_story_privacy", config.maximum_unsafe_story_privacy)
    maximum(
        "unexpected_or_unconsumed_provider_responses",
        config.maximum_unexpected_or_unconsumed_provider_responses,
    )
    maximum("maximum_model_calls_observed", config.maximum_model_calls_per_case)
    minimum("cleaner_fallback_cases", config.minimum_cleaner_fallback_cases)
    minimum("extractor_repair_cases", config.minimum_extractor_repair_cases)
    minimum("focused_partial_failure_cases", config.minimum_focused_partial_failure_cases)
    minimum("review_resolution_cases", config.minimum_review_resolution_cases)
    maximum("pipeline_version_failures", config.maximum_pipeline_version_failures)
    maximum("fatal_case_failures", config.maximum_fatal_case_failures)
    maximum("word_error_rate", config.maximum_word_error_rate)
    maximum("character_error_rate", config.maximum_character_error_rate)
    return E2EGateResult(passed=not failures, failures=failures, measurements=measurements)


def render_e2e_report(report: E2EReport, gate: E2EGateResult) -> str:
    lines = [
        "# Mura Offline End-to-End ML Evaluation",
        "",
        "> ASR and DeepSeek outputs are frozen external responses. This gate validates full ",
        "> orchestration, sanitization, provenance, resolution, failure handling, and version ",
        "> consistency. It does not measure live provider quality.",
        "",
    ]
    for name, value in sorted(gate.measurements.items()):
        lines.append(f"- {name}: `{value}`")
    lines.extend(["", f"## Gate: {'PASS' if gate.passed else 'FAIL'}"])
    lines.extend(f"- {failure}" for failure in gate.failures)
    lines.extend(["", "## Cases", ""])
    for case in report.cases:
        status = "PASS" if case.passed else "FAIL"
        lines.append(
            f"- `{case.case_id}` ({case.language.value}): **{status}**, "
            f"calls={case.model_calls}, digest=`{case.output_digest[:12]}`"
        )
        lines.extend(f"  - {failure}" for failure in case.failures)
    return "\n".join(lines)


def write_e2e_json(report: E2EReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
