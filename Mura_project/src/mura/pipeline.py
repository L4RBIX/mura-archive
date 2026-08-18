from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from mura.deepseek import DeepSeekPipelineService
from mura.domain.models import ExtractionResult, PipelineRequest, PipelineResult
from mura.entity_resolution import EntityResolutionContext, legacy_resolution_context
from mura.long_form import (
    LongFormCallBudget,
    LongFormExtractionPlanner,
    LongFormMode,
    LongFormPolicy,
    WindowPlan,
)
from mura.long_form_merge import WindowExtraction, merge_window_extractions
from mura.resolution import resolve_mentions_with_report
from mura.versioning import get_pipeline_versions

StageCallback = Callable[[str], None]


class MuraPipeline:
    def __init__(
        self,
        deepseek: DeepSeekPipelineService,
        *,
        long_form_policy: LongFormPolicy | None = None,
        long_form_budget: LongFormCallBudget | None = None,
    ) -> None:
        self.deepseek = deepseek
        self.long_form_planner = LongFormExtractionPlanner(long_form_policy)
        self.long_form_budget = long_form_budget or LongFormCallBudget()

    def process(
        self,
        request: PipelineRequest,
        *,
        stage_callback: StageCallback | None = None,
        resolution_context: EntityResolutionContext | None = None,
    ) -> PipelineResult:
        started = time.perf_counter()
        plan = self.long_form_planner.plan(request.transcript)
        if plan.mode is LongFormMode.SHORT:
            return self._process_short(
                request,
                plan=plan,
                started=started,
                stage_callback=stage_callback,
                resolution_context=resolution_context,
            )
        return self._process_long(
            request,
            plan=plan,
            started=started,
            stage_callback=stage_callback,
            resolution_context=resolution_context,
        )

    def _process_short(
        self,
        request: PipelineRequest,
        *,
        plan: WindowPlan,
        started: float,
        stage_callback: StageCallback | None,
        resolution_context: EntityResolutionContext | None,
    ) -> PipelineResult:
        self._report(stage_callback, "cleaning")
        cleaned, cleaner_usage = self.deepseek.clean(
            transcript=request.transcript,
            speaker_id=request.speaker_id,
            speaker_name=request.speaker_name,
        )
        self._report(stage_callback, "extracting")
        extraction, extractor_usage = self.deepseek.extract(
            transcript=request.transcript,
            cleaned=cleaned,
            speaker_id=request.speaker_id,
            speaker_name=request.speaker_name,
            known_people=request.known_people,
        )
        self._report(stage_callback, "resolving")
        resolved_context = resolution_context or legacy_resolution_context(request.known_people)
        resolution_run = resolve_mentions_with_report(extraction, resolved_context)

        return PipelineResult(
            transcript=request.transcript,
            cleaned_transcript=cleaned,
            extraction=extraction,
            resolutions=resolution_run.resolutions,
            processing={
                "total_seconds": round(time.perf_counter() - started, 3),
                "cleaner_usage": cleaner_usage,
                "extractor_usage": extractor_usage,
                "entity_resolution": resolution_run.model_dump(mode="json"),
                "long_form": {
                    "mode": LongFormMode.SHORT.value,
                    "status": "completed",
                    "plan": plan.model_dump(mode="json"),
                },
                "versions": get_pipeline_versions().model_dump(mode="json"),
            },
        )

    def _process_long(
        self,
        request: PipelineRequest,
        *,
        plan: WindowPlan,
        started: float,
        stage_callback: StageCallback | None,
        resolution_context: EntityResolutionContext | None,
    ) -> PipelineResult:
        self._report(stage_callback, "planning_long_form")
        successful: list[WindowExtraction] = []
        window_reports: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        model_calls = 0
        prompt_tokens = 0
        completion_tokens = 0
        budget_exhausted = len(plan.windows) > self.long_form_budget.maximum_windows

        for window in plan.windows:
            if budget_exhausted or self._budget_exhausted(
                started=started,
                model_calls=model_calls,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ):
                budget_exhausted = True
                issues.append(
                    {
                        "code": "long_form_window_budget_exhausted",
                        "window_id": window.window_id,
                    }
                )
                window_reports.append(
                    {
                        "window_id": window.window_id,
                        "ordinal": window.ordinal,
                        "status": "skipped",
                        "issue_code": "long_form_window_budget_exhausted",
                    }
                )
                continue

            window_started = time.perf_counter()
            window_transcript = self.long_form_planner.materialize_window(
                request.transcript,
                window,
            )
            self._report(stage_callback, f"window_{window.ordinal}_cleaning")
            cleaned, _cleaner_usage = self.deepseek.clean_raw_preserving(
                transcript=window_transcript
            )
            self._report(stage_callback, f"window_{window.ordinal}_extracting")
            try:
                extraction, usage = self.deepseek.extract_window(
                    transcript=window_transcript,
                    cleaned=cleaned,
                    speaker_id=request.speaker_id,
                    speaker_name=request.speaker_name,
                    known_people=request.known_people,
                    maximum_repairs=self.long_form_budget.maximum_repairs_per_window,
                )
                self._report(stage_callback, f"window_{window.ordinal}_validating")
            except Exception as exc:
                issue_code = self._window_error_code(exc)
                issues.append({"code": issue_code, "window_id": window.window_id})
                window_reports.append(
                    {
                        "window_id": window.window_id,
                        "ordinal": window.ordinal,
                        "status": "failed",
                        "issue_code": issue_code,
                        "processing_seconds": round(time.perf_counter() - window_started, 3),
                    }
                )
                self._report(stage_callback, f"window_{window.ordinal}_failed")
                continue

            calls, prompt, completion = self._usage_totals(usage)
            model_calls += calls
            prompt_tokens += prompt
            completion_tokens += completion
            successful.append(WindowExtraction(window=window, extraction=extraction))
            window_reports.append(
                {
                    "window_id": window.window_id,
                    "ordinal": window.ordinal,
                    "status": "completed",
                    "model_calls": calls,
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "accepted_objects": self._object_count(extraction),
                    "processing_seconds": round(time.perf_counter() - window_started, 3),
                }
            )
            self._report(stage_callback, f"window_{window.ordinal}_completed")

        if not successful:
            issue_codes = sorted({item["code"] for item in issues})
            raise RuntimeError(f"long-form extraction produced no safe windows: {issue_codes}")

        self._report(stage_callback, "merging_windows")
        merged, merge_report = merge_window_extractions(
            recording_id=request.transcript.recording_id,
            speaker_id=request.speaker_id,
            speaker_name=request.speaker_name,
            windows=successful,
        )
        full_cleaned, cleaner_usage = self.deepseek.clean_raw_preserving(
            transcript=request.transcript
        )
        self._report(stage_callback, "global_validation")
        global_outcome = self.deepseek.validate_merged_candidate(
            result=merged,
            transcript=request.transcript,
            cleaned=full_cleaned,
            speaker_id=request.speaker_id,
            speaker_name=request.speaker_name,
        )
        extraction = global_outcome.result
        issues.extend(global_outcome.issues)

        self._report(stage_callback, "resolving_entities")
        resolved_context = resolution_context or legacy_resolution_context(request.known_people)
        resolution_run = resolve_mentions_with_report(extraction, resolved_context)
        completed_windows = len(successful)
        failed_windows = sum(item["status"] == "failed" for item in window_reports)
        skipped_windows = sum(item["status"] == "skipped" for item in window_reports)
        status = (
            "partially_completed" if failed_windows or skipped_windows else "completed_with_review"
        )
        if not issues and not merge_report.review_required:
            status = "completed"

        extractor_usage = {
            "extraction_mode": "long_form_windowed",
            "model_calls": model_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "extraction_issues": issues,
            "accepted_objects": self._object_count(extraction),
            "quarantined_objects": sum(
                1 for item in global_outcome.issues if not item.get("recoverable", False)
            ),
        }
        return PipelineResult(
            transcript=request.transcript,
            cleaned_transcript=full_cleaned,
            extraction=extraction,
            resolutions=resolution_run.resolutions,
            processing={
                "total_seconds": round(time.perf_counter() - started, 3),
                "cleaner_usage": cleaner_usage,
                "extractor_usage": extractor_usage,
                "entity_resolution": resolution_run.model_dump(mode="json"),
                "long_form": {
                    "mode": LongFormMode.WINDOWED.value,
                    "status": status,
                    "plan": plan.model_dump(mode="json"),
                    "budget": self.long_form_budget.model_dump(mode="json"),
                    "total_windows": len(plan.windows),
                    "completed_windows": completed_windows,
                    "failed_windows": failed_windows,
                    "skipped_windows": skipped_windows,
                    "percentage": round(100 * completed_windows / len(plan.windows), 1),
                    "safe_partial_archive": completed_windows > 0,
                    "retry_required": failed_windows + skipped_windows > 0,
                    "retryable_window_ids": [
                        item["window_id"]
                        for item in window_reports
                        if item["status"] in {"failed", "skipped"}
                    ],
                    "window_reports": window_reports,
                    "merge": merge_report.model_dump(mode="json"),
                    "issue_codes": sorted(
                        {item.get("code", "long_form_window_failed") for item in issues}
                    ),
                },
                "versions": get_pipeline_versions().model_dump(mode="json"),
            },
        )

    def _budget_exhausted(
        self,
        *,
        started: float,
        model_calls: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> bool:
        budget = self.long_form_budget
        return (
            model_calls >= budget.maximum_total_model_calls
            or prompt_tokens >= budget.maximum_total_prompt_tokens
            or completion_tokens >= budget.maximum_total_completion_tokens
            or time.perf_counter() - started >= budget.maximum_processing_seconds
        )

    @staticmethod
    def _usage_totals(usage: dict[str, Any]) -> tuple[int, int, int]:
        calls = int(usage.get("model_calls", 1))
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        initial = usage.get("initial_usage")
        if isinstance(initial, dict):
            prompt += int(initial.get("prompt_tokens") or 0)
            completion += int(initial.get("completion_tokens") or 0)
        return calls, prompt, completion

    @staticmethod
    def _object_count(extraction: ExtractionResult) -> int:
        return sum(
            len(items)
            for items in (
                extraction.people_mentions,
                extraction.relationship_claims,
                extraction.events,
                extraction.descriptions,
                extraction.stories,
                extraction.unresolved_questions,
            )
        )

    @staticmethod
    def _window_error_code(exc: Exception) -> str:
        name = type(exc).__name__.casefold()
        if "timeout" in name:
            return "long_form_window_timeout"
        return "long_form_window_failed"

    @staticmethod
    def _report(callback: StageCallback | None, stage: str) -> None:
        if callback is not None:
            callback(stage)
