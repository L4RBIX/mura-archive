from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from mura.domain.models import (
    CleanerResult,
    ExtractionResult,
    PipelineRequest,
    RawSegment,
    ReadableSegment,
    TranscriptEnvelope,
)
from mura.long_form import LongFormCallBudget
from mura.pipeline import MuraPipeline


def _transcript() -> TranscriptEnvelope:
    segments = [
        RawSegment(
            segment_id=f"seg_{index:02d}",
            start=float(index * 10),
            end=float(index * 10 + 8),
            text=f"Бұл {index} сегмент. Семья туралы рассказ продолжается.",
        )
        for index in range(18)
    ]
    return TranscriptEnvelope(
        recording_id="rec_pipeline_long",
        duration_seconds=180,
        language_hints=["kk", "ru"],
        full_text=" ".join(item.text for item in segments),
        segments=segments,
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


class FakeDeepSeek:
    def __init__(self, *, fail_call: int | None = None) -> None:
        self.calls = 0
        self.fail_call = fail_call
        self.observed_maximum_repairs: list[int] = []

    def clean_raw_preserving(
        self, *, transcript: TranscriptEnvelope
    ) -> tuple[CleanerResult, dict[str, Any]]:
        return CleanerResult(
            readable_segments=[
                ReadableSegment(segment_id=item.segment_id, text=item.text)
                for item in transcript.segments
            ],
            full_readable_text=transcript.full_text,
        ), {"model_calls": 0}

    def extract_window(
        self,
        *,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
        known_people: list[object],
        maximum_repairs: int = 1,
    ) -> tuple[ExtractionResult, dict[str, Any]]:
        del cleaned, known_people
        self.observed_maximum_repairs.append(maximum_repairs)
        self.calls += 1
        if self.calls == self.fail_call:
            raise TimeoutError("provider timeout")
        return ExtractionResult(
            recording_id=transcript.recording_id,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            languages=["kk", "ru"],
        ), {
            "model_calls": 1,
            "prompt_tokens": 100,
            "completion_tokens": 20,
        }

    def validate_merged_candidate(
        self,
        *,
        result: ExtractionResult,
        transcript: TranscriptEnvelope,
        cleaned: CleanerResult,
        speaker_id: str,
        speaker_name: str,
    ) -> SimpleNamespace:
        del transcript, cleaned, speaker_id, speaker_name
        return SimpleNamespace(result=result, issues=[])


def test_long_form_pipeline_reports_progress_and_completes_all_windows() -> None:
    stages: list[str] = []
    pipeline = MuraPipeline(FakeDeepSeek())  # type: ignore[arg-type]

    result = pipeline.process(
        PipelineRequest(
            transcript=_transcript(),
            speaker_id="speaker",
            speaker_name="Narrator",
        ),
        stage_callback=stages.append,
    )

    metadata = result.processing["long_form"]
    assert metadata["status"] == "completed"
    assert metadata["completed_windows"] == metadata["total_windows"]
    assert stages[0] == "planning_long_form"
    assert "merging_windows" in stages
    assert "global_validation" in stages
    assert stages[-1] == "resolving_entities"
    assert result.processing["extractor_usage"]["model_calls"] == metadata["total_windows"]


def test_middle_window_timeout_keeps_successful_windows_and_marks_partial() -> None:
    pipeline = MuraPipeline(FakeDeepSeek(fail_call=2))  # type: ignore[arg-type]

    result = pipeline.process(
        PipelineRequest(
            transcript=_transcript(),
            speaker_id="speaker",
            speaker_name="Narrator",
        )
    )

    metadata = result.processing["long_form"]
    assert metadata["status"] == "partially_completed"
    assert metadata["failed_windows"] == 1
    assert metadata["completed_windows"] == metadata["total_windows"] - 1
    assert "long_form_window_timeout" in metadata["issue_codes"]
    assert metadata["safe_partial_archive"] is True
    assert len(metadata["retryable_window_ids"]) == 1


def test_budget_exhaustion_skips_remaining_windows_without_losing_first_result() -> None:
    pipeline = MuraPipeline(
        FakeDeepSeek(),  # type: ignore[arg-type]
        long_form_budget=LongFormCallBudget(maximum_total_model_calls=1),
    )

    result = pipeline.process(
        PipelineRequest(
            transcript=_transcript(),
            speaker_id="speaker",
            speaker_name="Narrator",
        )
    )

    metadata = result.processing["long_form"]
    assert metadata["completed_windows"] == 1
    assert metadata["skipped_windows"] == metadata["total_windows"] - 1
    assert "long_form_window_budget_exhausted" in metadata["issue_codes"]


def test_budget_rejects_a_configuration_without_a_primary_logical_call() -> None:
    with pytest.raises(ValidationError):
        LongFormCallBudget(maximum_primary_calls_per_window=0)


def test_default_budget_offers_each_window_one_logical_repair() -> None:
    deepseek = FakeDeepSeek()
    pipeline = MuraPipeline(deepseek)  # type: ignore[arg-type]

    pipeline.process(
        PipelineRequest(
            transcript=_transcript(),
            speaker_id="speaker",
            speaker_name="Narrator",
        )
    )

    assert deepseek.observed_maximum_repairs
    assert set(deepseek.observed_maximum_repairs) == {1}


def test_zero_repair_budget_is_propagated_to_every_window() -> None:
    deepseek = FakeDeepSeek()
    pipeline = MuraPipeline(
        deepseek,  # type: ignore[arg-type]
        long_form_budget=LongFormCallBudget(maximum_repairs_per_window=0),
    )

    pipeline.process(
        PipelineRequest(
            transcript=_transcript(),
            speaker_id="speaker",
            speaker_name="Narrator",
        )
    )

    assert deepseek.observed_maximum_repairs
    assert set(deepseek.observed_maximum_repairs) == {0}
