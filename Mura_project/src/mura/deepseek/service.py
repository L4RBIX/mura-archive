from __future__ import annotations

from dataclasses import asdict
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from mura.deepseek.anchor_prompts import (
    ANCHOR_CONSTRAINED_EXTRACTION_REPAIR_SYSTEM_PROMPT,
    ANCHOR_CONSTRAINED_EXTRACTOR_SYSTEM_PROMPT,
    FOCUSED_CORE_EXTRACTOR_SYSTEM_PROMPT,
    FOCUSED_CORE_REPAIR_SYSTEM_PROMPT,
    FOCUSED_EVENT_EXTRACTOR_SYSTEM_PROMPT,
    FOCUSED_EVENT_REPAIR_SYSTEM_PROMPT,
    FOCUSED_STORY_EXTRACTOR_SYSTEM_PROMPT,
    FOCUSED_STORY_REPAIR_SYSTEM_PROMPT,
)
from mura.deepseek.anchors import ExtractionAnchorBundle, build_extraction_anchor_bundle
from mura.deepseek.client import DeepSeekClient, DeepSeekError, DeepSeekUsage
from mura.deepseek.extraction_telemetry import build_extraction_telemetry
from mura.deepseek.focused_extraction import (
    FocusedExtractionPass,
    accepted_context,
    empty_extraction_raw,
    merge_focused_pass,
    pass_output_schema,
    validate_pass_identity,
)
from mura.deepseek.prompts import CLEANER_REPAIR_SYSTEM_PROMPT, CLEANER_SYSTEM_PROMPT
from mura.domain.models import (
    CleanerResult,
    ExtractionResult,
    KnownPerson,
    ReadableSegment,
    TranscriptEnvelope,
)
from mura.extraction_issues import (
    ExtractionIssue,
    ExtractionIssueCode,
    IssueSeverity,
    IssueStage,
    safe_issue_counts,
)
from mura.extraction_sanitizer import (
    ExtractionSanitizationOutcome,
    process_extraction_candidate,
)
from mura.validation import ContractValidationError, validate_cleaner_result

ModelT = TypeVar("ModelT", bound=BaseModel)
_FATAL_EXTRACTION_COLLECTIONS = frozenset(
    {
        "people_mentions",
        "relationship_claims",
        "events",
        "descriptions",
        "stories",
        "unresolved_questions",
    }
)


class DeepSeekPipelineService:
    def __init__(self, client: DeepSeekClient, *, focused_extraction: bool = False) -> None:
        self.client = client
        self.focused_extraction = focused_extraction

    def clean(
        self,
        *,
        transcript: TranscriptEnvelope,
        speaker_id: str,
        speaker_name: str,
    ) -> tuple[CleanerResult, dict[str, Any]]:
        payload = {
            "recording_id": transcript.recording_id,
            "speaker": {"speaker_id": speaker_id, "speaker_name": speaker_name},
            "output_schema": CleanerResult.model_json_schema(),
            "segments": [segment.model_dump() for segment in transcript.segments],
        }
        raw, usage = self.client.request_json(
            system_prompt=CLEANER_SYSTEM_PROMPT,
            payload=payload,
            max_tokens=12_000,
        )
        initial_usage = self._usage_dict(usage)
        try:
            result = self._validate_model(CleanerResult, raw, "cleaner")
            validate_cleaner_result(transcript, result)
        except (DeepSeekError, ContractValidationError):
            try:
                result, repair_usage = self._repair_cleaner(
                    transcript=transcript,
                    invalid_output=raw,
                    validation_failures=[{"code": "cleaner_contract_invalid"}],
                )
            except (DeepSeekError, ContractValidationError):
                fallback = self._raw_preserving_cleaner_fallback(transcript)
                return fallback, {
                    **initial_usage,
                    "repair_attempted": True,
                    "repair_succeeded": False,
                    "fallback_used": True,
                    "fallback_strategy": "raw_transcript",
                    "validation_issue_counts": {
                        "cleaner_contract_invalid": 1,
                        "cleaner_repair_failed": 1,
                    },
                    "initial_usage": initial_usage,
                }
            return result, {
                **repair_usage,
                "repair_attempted": True,
                "repair_succeeded": True,
                "fallback_used": False,
                "validation_issue_counts": {"cleaner_contract_invalid": 1},
                "initial_usage": initial_usage,
            }
        return result, {
            **initial_usage,
            "repair_attempted": False,
            "repair_succeeded": False,
            "fallback_used": False,
            "validation_issue_counts": {},
        }

    def _repair_cleaner(
        self,
        *,
        transcript: TranscriptEnvelope,
        invalid_output: dict[str, Any],
        validation_failures: list[dict[str, str]],
    ) -> tuple[CleanerResult, dict[str, Any]]:
        repair_payload = {
            "validation_failures": validation_failures,
            "output_schema": CleanerResult.model_json_schema(),
            "previous_untrusted_output": invalid_output,
            "allowed_segment_ids": [segment.segment_id for segment in transcript.segments],
            "raw_segments": [segment.model_dump() for segment in transcript.segments],
        }
        repaired_raw, repair_usage = self.client.request_json(
            system_prompt=CLEANER_REPAIR_SYSTEM_PROMPT,
            payload=repair_payload,
            max_tokens=12_000,
            attempts=2,
        )
        repaired = self._validate_model(CleanerResult, repaired_raw, "cleaner_repair")
        validate_cleaner_result(transcript, repaired)
        return repaired, self._usage_dict(repair_usage)

    @staticmethod
    def _raw_preserving_cleaner_fallback(transcript: TranscriptEnvelope) -> CleanerResult:
        fallback = CleanerResult(
            readable_segments=[
                ReadableSegment(segment_id=segment.segment_id, text=segment.text)
                for segment in transcript.segments
            ],
            detected_corrections=[],
            uncertain_fragments=[],
            full_readable_text=" ".join(segment.text for segment in transcript.segments),
        )
        validate_cleaner_result(transcript, fallback)
        return fallback

    def clean_raw_preserving(
        self,
        *,
        transcript: TranscriptEnvelope,
    ) -> tuple[CleanerResult, dict[str, Any]]:
        """Return the deterministic source-preserving cleaner used by bounded windows."""

        return self._raw_preserving_cleaner_fallback(transcript), {
            "model_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "repair_attempted": False,
            "repair_succeeded": False,
            "fallback_used": True,
            "fallback_strategy": "raw_transcript",
        }

    def extract(
        self,
        *,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
        known_people: list[KnownPerson] | None = None,
    ) -> tuple[ExtractionResult, dict[str, Any]]:
        if self.focused_extraction:
            return self._extract_focused(
                transcript=transcript,
                cleaned=cleaned,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                known_people=known_people,
            )
        return self._extract_single(
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            known_people=known_people,
        )

    def _extract_single(
        self,
        *,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
        known_people: list[KnownPerson] | None = None,
        maximum_repairs: int = 1,
    ) -> tuple[ExtractionResult, dict[str, Any]]:
        """Run one primary extraction call plus at most ``maximum_repairs`` logical repairs.

        ``maximum_repairs`` is a ceiling on logical repair operations, not on the
        transport attempts ``request_json`` performs internally.
        """

        resolved_known_people = known_people or []
        anchors = build_extraction_anchor_bundle(
            transcript=transcript,
            cleaned=cleaned,
            speaker_name=speaker_name,
            known_people=resolved_known_people,
        )
        payload = self._extraction_payload(
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            known_people=resolved_known_people,
            anchors=anchors,
        )
        raw, usage = self.client.request_json(
            system_prompt=ANCHOR_CONSTRAINED_EXTRACTOR_SYSTEM_PROMPT,
            payload=payload,
            max_tokens=16_000,
        )
        initial_usage = self._usage_dict(usage)
        repair_attempted = False
        repair_succeeded = False
        initial_outcome: ExtractionSanitizationOutcome | None = None

        try:
            outcome = self._process_extraction_candidate(
                raw=raw,
                transcript=transcript,
                cleaned=cleaned,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
            )
        except (ValidationError, ContractValidationError):
            if maximum_repairs < 1:
                raise
            failures = [{"code": "final_contract_invalid", "stage": "provenance"}]
            outcome, usage = self._repair_extraction(
                transcript=transcript,
                cleaned=cleaned,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                known_people=resolved_known_people,
                anchors=anchors,
                invalid_output=raw,
                validation_failures=failures,
            )
            repair_attempted = True
            repair_succeeded = True
        else:
            initial_outcome = outcome
            if maximum_repairs >= 1 and self._requires_extraction_repair(
                raw=outcome.recovered_raw,
                result=outcome.result,
                extraction_issues=outcome.issues,
            ):
                outcome, usage = self._repair_extraction(
                    transcript=transcript,
                    cleaned=cleaned,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                    known_people=resolved_known_people,
                    anchors=anchors,
                    invalid_output=raw,
                    validation_failures=self._repair_failures(outcome.issues),
                )
                repair_attempted = True
                repair_succeeded = True

        telemetry = build_extraction_telemetry(
            raw=outcome.recovered_raw,
            usage=usage,
            result=outcome.result,
            extraction_issues=outcome.issues,
            evidence_closure_count=outcome.evidence_closure_count,
            evidence_recovery=outcome.evidence_recovery,
            transcript=transcript,
            anchor_schema_version=anchors.schema_version,
            allowed_segment_count=len(anchors.allowed_segment_ids),
            mention_anchor_count=len(anchors.mention_anchors),
            lexical_annotation_count=len(anchors.lexical_annotations),
            repair_attempted=repair_attempted,
            repair_succeeded=repair_succeeded,
        ).model_dump(mode="json")
        telemetry["repaired_evidence_offsets"] = outcome.evidence_recovery.repaired_evidence_offsets
        if repair_attempted:
            telemetry["initial_usage"] = initial_usage
            if initial_outcome is not None:
                telemetry["initial_evidence_offset_recovery"] = (
                    initial_outcome.evidence_recovery.to_dict()
                )
                telemetry["initial_validation_issue_counts"] = safe_issue_counts(
                    initial_outcome.issues
                )
        return outcome.result, telemetry

    def extract_window(
        self,
        *,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
        known_people: list[KnownPerson] | None = None,
        maximum_repairs: int = 1,
    ) -> tuple[ExtractionResult, dict[str, Any]]:
        """Run the bounded single-pass policy regardless of the short-path focused setting."""

        result, telemetry = self._extract_single(
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            known_people=known_people,
            maximum_repairs=maximum_repairs,
        )
        telemetry["extraction_mode"] = "long_form_window_single_pass"
        telemetry["model_calls"] = 1 + int(bool(telemetry.get("repair_attempted")))
        return result, telemetry

    def validate_merged_candidate(
        self,
        *,
        result: ExtractionResult,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
    ) -> ExtractionSanitizationOutcome:
        """Apply the normal sanitizer and provenance contract once after global merge."""

        return self._process_extraction_candidate(
            raw=result.model_dump(mode="json"),
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )

    def _extract_focused(
        self,
        *,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
        known_people: list[KnownPerson] | None = None,
    ) -> tuple[ExtractionResult, dict[str, Any]]:
        resolved_known_people = known_people or []
        anchors = build_extraction_anchor_bundle(
            transcript=transcript,
            cleaned=cleaned,
            speaker_name=speaker_name,
            known_people=resolved_known_people,
        )
        empty_raw = empty_extraction_raw(
            recording_id=transcript.recording_id,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )
        current_outcome = self._process_extraction_candidate(
            raw=empty_raw,
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )
        current_raw = current_outcome.result.model_dump(mode="json")
        usages: list[DeepSeekUsage] = []
        pass_reports: list[dict[str, Any]] = []
        collected_issues: list[dict[str, Any]] = []

        for pass_name in (
            FocusedExtractionPass.CORE,
            FocusedExtractionPass.EVENTS,
            FocusedExtractionPass.STORIES,
        ):
            current_outcome, current_raw, pass_usages, report = self._run_focused_pass(
                pass_name=pass_name,
                base_outcome=current_outcome,
                base_raw=current_raw,
                transcript=transcript,
                cleaned=cleaned,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                known_people=resolved_known_people,
                anchors=anchors,
            )
            usages.extend(pass_usages)
            pass_reports.append(report)
            collected_issues.extend(report.get("issues", []))

        all_issues = self._deduplicate_issue_payloads([*collected_issues, *current_outcome.issues])
        aggregate_usage = self._aggregate_usage(usages)
        repair_reports = [report for report in pass_reports if report["repair_attempted"]]
        telemetry = build_extraction_telemetry(
            raw=current_raw,
            usage=aggregate_usage,
            result=current_outcome.result,
            extraction_issues=all_issues,
            evidence_closure_count=current_outcome.evidence_closure_count,
            evidence_recovery=current_outcome.evidence_recovery,
            transcript=transcript,
            anchor_schema_version=anchors.schema_version,
            allowed_segment_count=len(anchors.allowed_segment_ids),
            mention_anchor_count=len(anchors.mention_anchors),
            lexical_annotation_count=len(anchors.lexical_annotations),
            repair_attempted=bool(repair_reports),
            repair_succeeded=bool(repair_reports)
            and all(report["repair_succeeded"] for report in repair_reports),
        ).model_dump(mode="json")
        telemetry.update(
            {
                "extraction_mode": "focused",
                "focused_passes": [
                    {key: value for key, value in report.items() if key != "issues"}
                    for report in pass_reports
                ],
                "focused_primary_calls": 3,
                "focused_repair_calls": len(repair_reports),
                "focused_call_budget": 6,
                "focused_partial_failures": sum(
                    report["status"] == "failed" for report in pass_reports
                ),
                "repaired_evidence_offsets": (
                    current_outcome.evidence_recovery.repaired_evidence_offsets
                ),
            }
        )
        return current_outcome.result, telemetry

    def _run_focused_pass(
        self,
        *,
        pass_name: FocusedExtractionPass,
        base_outcome: ExtractionSanitizationOutcome,
        base_raw: dict[str, Any],
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
        known_people: list[KnownPerson],
        anchors: ExtractionAnchorBundle,
    ) -> tuple[
        ExtractionSanitizationOutcome,
        dict[str, Any],
        list[DeepSeekUsage],
        dict[str, Any],
    ]:
        payload = self._focused_pass_payload(
            pass_name=pass_name,
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            known_people=known_people,
            anchors=anchors,
            accepted_result=base_outcome.result,
        )
        usages: list[DeepSeekUsage] = []
        issues: list[dict[str, Any]] = []
        repair_attempted = False
        repair_succeeded = False
        merge_metrics: dict[str, int] = {}
        primary_raw: dict[str, Any] | None = None

        try:
            primary_raw, primary_usage = self.client.request_json(
                system_prompt=self._focused_prompt(pass_name, repair=False),
                payload=payload,
                max_tokens=self._focused_max_tokens(pass_name),
            )
            usages.append(primary_usage)
            outcome, _merged_raw, merge_metrics = self._process_focused_pass_candidate(
                pass_name=pass_name,
                pass_raw=primary_raw,
                base_raw=base_raw,
                transcript=transcript,
                cleaned=cleaned,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
            )
        except (DeepSeekError, ValidationError, ContractValidationError, ValueError):
            repair_attempted = primary_raw is not None
            if primary_raw is None:
                issue = self._focused_pass_issue(pass_name, repair=False)
                issues.append(issue)
                return (
                    base_outcome,
                    base_raw,
                    usages,
                    self._focused_pass_report(
                        pass_name=pass_name,
                        status="failed",
                        usages=usages,
                        repair_attempted=False,
                        repair_succeeded=False,
                        merge_metrics={},
                        outcome=base_outcome,
                        issues=issues,
                    ),
                )
            repair_payload = {
                **payload,
                "validation_failures": [
                    {
                        "code": ExtractionIssueCode.FOCUSED_PASS_CONTRACT_INVALID.value,
                        "stage": IssueStage.SCHEMA.value,
                        "object_type": f"focused_{pass_name.value}_pass",
                    }
                ],
                "previous_untrusted_output": primary_raw,
            }
            try:
                repaired_raw, repair_usage = self.client.request_json(
                    system_prompt=self._focused_prompt(pass_name, repair=True),
                    payload=repair_payload,
                    max_tokens=self._focused_max_tokens(pass_name),
                    attempts=2,
                )
                usages.append(repair_usage)
                outcome, _merged_raw, merge_metrics = self._process_focused_pass_candidate(
                    pass_name=pass_name,
                    pass_raw=repaired_raw,
                    base_raw=base_raw,
                    transcript=transcript,
                    cleaned=cleaned,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                )
                repair_succeeded = True
            except (DeepSeekError, ValidationError, ContractValidationError, ValueError):
                issue = self._focused_pass_issue(pass_name, repair=True)
                issues.append(issue)
                return (
                    base_outcome,
                    base_raw,
                    usages,
                    self._focused_pass_report(
                        pass_name=pass_name,
                        status="failed",
                        usages=usages,
                        repair_attempted=True,
                        repair_succeeded=False,
                        merge_metrics={},
                        outcome=base_outcome,
                        issues=issues,
                    ),
                )

        if any(value > 0 for value in merge_metrics.values()):
            issues.append(
                ExtractionIssue.create(
                    stage=IssueStage.SEMANTIC,
                    object_type=f"focused_{pass_name.value}_pass",
                    object_id=pass_name.value,
                    code=ExtractionIssueCode.DUPLICATE_SEMANTIC_OBJECT,
                    severity=IssueSeverity.WARNING,
                    recoverable=True,
                    related_ids=[key for key, value in merge_metrics.items() if value > 0],
                ).to_dict()
            )
        issues.extend(outcome.issues)
        return (
            outcome,
            outcome.result.model_dump(mode="json"),
            usages,
            self._focused_pass_report(
                pass_name=pass_name,
                status="completed",
                usages=usages,
                repair_attempted=repair_attempted,
                repair_succeeded=repair_succeeded,
                merge_metrics=merge_metrics,
                outcome=outcome,
                issues=issues,
            ),
        )

    def _process_focused_pass_candidate(
        self,
        *,
        pass_name: FocusedExtractionPass,
        pass_raw: dict[str, Any],
        base_raw: dict[str, Any],
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
    ) -> tuple[ExtractionSanitizationOutcome, dict[str, Any], dict[str, int]]:
        validate_pass_identity(
            pass_name,
            pass_raw,
            recording_id=transcript.recording_id,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )
        merged_raw, merge_metrics = merge_focused_pass(base_raw, pass_name, pass_raw)
        outcome = self._process_extraction_candidate(
            raw=merged_raw,
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )
        return outcome, merged_raw, merge_metrics.to_dict()

    def _focused_pass_payload(
        self,
        *,
        pass_name: FocusedExtractionPass,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
        known_people: list[KnownPerson],
        anchors: ExtractionAnchorBundle,
        accepted_result: ExtractionResult,
    ) -> dict[str, Any]:
        payload = self._extraction_payload(
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            known_people=known_people,
            anchors=anchors,
        )
        payload["output_schema"] = pass_output_schema(pass_name)
        payload["focused_pass"] = {
            "name": pass_name.value,
            "primary_pass_limit": 3,
            "repair_limit_per_pass": 1,
            "evidence_namespace": f"{pass_name.value}__",
        }
        if pass_name is not FocusedExtractionPass.CORE:
            payload.update(accepted_context(accepted_result, pass_name))
        return payload

    @staticmethod
    def _focused_prompt(pass_name: FocusedExtractionPass, *, repair: bool) -> str:
        prompts = {
            (FocusedExtractionPass.CORE, False): FOCUSED_CORE_EXTRACTOR_SYSTEM_PROMPT,
            (FocusedExtractionPass.CORE, True): FOCUSED_CORE_REPAIR_SYSTEM_PROMPT,
            (FocusedExtractionPass.EVENTS, False): FOCUSED_EVENT_EXTRACTOR_SYSTEM_PROMPT,
            (FocusedExtractionPass.EVENTS, True): FOCUSED_EVENT_REPAIR_SYSTEM_PROMPT,
            (FocusedExtractionPass.STORIES, False): FOCUSED_STORY_EXTRACTOR_SYSTEM_PROMPT,
            (FocusedExtractionPass.STORIES, True): FOCUSED_STORY_REPAIR_SYSTEM_PROMPT,
        }
        return prompts[(pass_name, repair)]

    @staticmethod
    def _focused_max_tokens(pass_name: FocusedExtractionPass) -> int:
        return {
            FocusedExtractionPass.CORE: 10_000,
            FocusedExtractionPass.EVENTS: 8_000,
            FocusedExtractionPass.STORIES: 7_000,
        }[pass_name]

    @staticmethod
    def _focused_pass_issue(
        pass_name: FocusedExtractionPass,
        *,
        repair: bool,
    ) -> dict[str, Any]:
        return ExtractionIssue.create(
            stage=IssueStage.REPAIR if repair else IssueStage.SCHEMA,
            object_type=f"focused_{pass_name.value}_pass",
            object_id=None,
            code=ExtractionIssueCode.FOCUSED_PASS_FAILED,
            severity=IssueSeverity.ERROR,
            recoverable=True,
        ).to_dict()

    @staticmethod
    def _focused_pass_report(
        *,
        pass_name: FocusedExtractionPass,
        status: str,
        usages: list[DeepSeekUsage],
        repair_attempted: bool,
        repair_succeeded: bool,
        merge_metrics: dict[str, int],
        outcome: ExtractionSanitizationOutcome,
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        collections = {
            FocusedExtractionPass.CORE: (
                len(outcome.result.people_mentions),
                len(outcome.result.relationship_claims),
            ),
            FocusedExtractionPass.EVENTS: (
                len(outcome.result.events),
                len(outcome.result.descriptions),
            ),
            FocusedExtractionPass.STORIES: (
                len(outcome.result.stories),
                len(outcome.result.unresolved_questions),
            ),
        }[pass_name]
        return {
            "pass": pass_name.value,
            "status": status,
            "request_count": len(usages),
            "repair_attempted": repair_attempted,
            "repair_succeeded": repair_succeeded,
            "accepted_primary_objects": collections[0],
            "accepted_secondary_objects": collections[1],
            "request_seconds": round(sum(item.request_seconds for item in usages), 3),
            "prompt_tokens": DeepSeekPipelineService._sum_usage(usages, "prompt_tokens"),
            "completion_tokens": DeepSeekPipelineService._sum_usage(usages, "completion_tokens"),
            "total_tokens": DeepSeekPipelineService._sum_usage(usages, "total_tokens"),
            "issue_counts": safe_issue_counts(issues),
            "merge_metrics": merge_metrics,
            "issues": issues,
        }

    @staticmethod
    def _sum_usage(usages: list[DeepSeekUsage], field_name: str) -> int | None:
        values = [getattr(item, field_name) for item in usages]
        present = [value for value in values if isinstance(value, int)]
        return sum(present) if present else None

    @classmethod
    def _aggregate_usage(cls, usages: list[DeepSeekUsage]) -> DeepSeekUsage:
        if not usages:
            return DeepSeekUsage(
                model="focused-no-provider-result",
                finish_reason=None,
                request_seconds=0.0,
            )
        return DeepSeekUsage(
            model=usages[-1].model,
            finish_reason=usages[-1].finish_reason,
            request_seconds=round(sum(item.request_seconds for item in usages), 3),
            prompt_tokens=cls._sum_usage(usages, "prompt_tokens"),
            completion_tokens=cls._sum_usage(usages, "completion_tokens"),
            total_tokens=cls._sum_usage(usages, "total_tokens"),
            prompt_cache_hit_tokens=cls._sum_usage(usages, "prompt_cache_hit_tokens"),
            prompt_cache_miss_tokens=cls._sum_usage(usages, "prompt_cache_miss_tokens"),
        )

    @staticmethod
    def _deduplicate_issue_payloads(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for issue in issues:
            key = (
                issue.get("stage"),
                issue.get("object_type"),
                issue.get("object_id"),
                issue.get("code"),
                tuple(issue.get("related_ids", [])),
            )
            if key in seen:
                continue
            seen.add(key)
            accepted.append(issue)
        return accepted

    @staticmethod
    def _process_extraction_candidate(
        *,
        raw: dict[str, Any],
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
    ) -> ExtractionSanitizationOutcome:
        """Single typed deterministic post-processing path shared by normal and repair flows."""

        return process_extraction_candidate(
            raw=raw,
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )

    @staticmethod
    def _extraction_payload(
        *,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
        known_people: list[KnownPerson],
        anchors: ExtractionAnchorBundle,
    ) -> dict[str, Any]:
        return {
            "recording_id": transcript.recording_id,
            "speaker": {"speaker_id": speaker_id, "speaker_name": speaker_name},
            "known_people": [person.model_dump(mode="json") for person in known_people],
            "anchor_contract": anchors.model_dump(mode="json"),
            "output_schema": ExtractionResult.model_json_schema(),
            "raw_segments": [segment.model_dump(mode="json") for segment in transcript.segments],
            "readable_segments": [
                segment.model_dump(mode="json") for segment in cleaned.readable_segments
            ],
            "detected_corrections": [
                correction.model_dump(mode="json") for correction in cleaned.detected_corrections
            ],
            "uncertain_fragments": [
                fragment.model_dump(mode="json") for fragment in cleaned.uncertain_fragments
            ],
            "full_readable_text": cleaned.full_readable_text,
        }

    def _repair_extraction(
        self,
        *,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
        known_people: list[KnownPerson],
        anchors: ExtractionAnchorBundle,
        invalid_output: dict[str, Any],
        validation_failures: list[dict[str, str]],
    ) -> tuple[ExtractionSanitizationOutcome, DeepSeekUsage]:
        repair_payload = {
            **self._extraction_payload(
                transcript=transcript,
                cleaned=cleaned,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                known_people=known_people,
                anchors=anchors,
            ),
            "validation_failures": validation_failures,
            "previous_untrusted_output": invalid_output,
        }
        repaired_raw, repair_usage = self.client.request_json(
            system_prompt=ANCHOR_CONSTRAINED_EXTRACTION_REPAIR_SYSTEM_PROMPT,
            payload=repair_payload,
            max_tokens=16_000,
            attempts=2,
        )
        outcome = self._process_extraction_candidate(
            raw=repaired_raw,
            transcript=transcript,
            cleaned=cleaned,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )
        return outcome, repair_usage

    @staticmethod
    def _requires_extraction_repair(
        *,
        raw: dict[str, Any],
        result: ExtractionResult,
        extraction_issues: list[dict[str, Any]],
    ) -> bool:
        accepted_objects = sum(
            len(items)
            for items in (
                result.people_mentions,
                result.relationship_claims,
                result.events,
                result.descriptions,
                result.stories,
                result.unresolved_questions,
            )
        )
        if accepted_objects:
            return False
        fatal_schema_issue = any(
            issue.get("code") == "top_level_not_list"
            and issue.get("object_type") in _FATAL_EXTRACTION_COLLECTIONS
            for issue in extraction_issues
        )
        model_attempted_content = any(
            raw.get(key) not in (None, []) for key in _FATAL_EXTRACTION_COLLECTIONS
        )
        return fatal_schema_issue and model_attempted_content

    @staticmethod
    def _repair_failures(extraction_issues: list[dict[str, Any]]) -> list[dict[str, str]]:
        failures: list[dict[str, str]] = []
        for issue in extraction_issues:
            if issue.get("severity") != "fatal":
                continue
            code = issue.get("code")
            stage = issue.get("stage")
            object_type = issue.get("object_type")
            if isinstance(code, str) and isinstance(stage, str) and isinstance(object_type, str):
                failures.append({"code": code, "stage": stage, "object_type": object_type})
        return failures or [{"code": "fatal_extraction_contract", "stage": "schema"}]

    @staticmethod
    def _validate_model(model_type: type[ModelT], raw: dict[str, Any], stage: str) -> ModelT:
        try:
            return model_type.model_validate(raw)
        except ValidationError as exc:
            raise DeepSeekError(f"{stage} JSON failed contract validation") from exc

    @staticmethod
    def _usage_dict(usage: DeepSeekUsage) -> dict[str, Any]:
        return asdict(usage)
