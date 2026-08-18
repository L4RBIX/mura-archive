from __future__ import annotations

import hashlib
import itertools
import math
import re
from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field, model_validator

from mura.domain.models import RawSegment, StrictModel, TranscriptEnvelope

PLANNER_VERSION = "long-form-planner-v1"
WINDOW_POLICY_VERSION = "long-form-window-policy-v1"


class LongFormMode(StrEnum):
    SHORT = "short"
    WINDOWED = "windowed"


class LongFormPolicy(StrictModel):
    """Versioned, deterministic thresholds for selecting and planning the long-form path."""

    planner_version: str = PLANNER_VERSION
    window_policy_version: str = WINDOW_POLICY_VERSION
    segment_count_threshold: int = Field(default=12, ge=2)
    normalized_token_threshold: int = Field(default=1_200, ge=128)
    estimated_input_token_threshold: int = Field(default=6_000, ge=128)
    maximum_segment_tokens: int = Field(default=480, ge=64)
    model_context_tokens: int = Field(default=32_768, ge=4_096)
    expected_schema_tokens: int = Field(default=9_000, ge=1_000)
    prompt_overhead_tokens: int = Field(default=2_000, ge=256)
    target_window_tokens: int = Field(default=1_450, ge=128)
    maximum_window_tokens: int = Field(default=1_900, ge=256)
    target_segments_per_window: int = Field(default=6, ge=2)
    maximum_windows: int = Field(default=6, ge=1, le=32)
    overlap_segments: int = Field(default=1, ge=0, le=2)
    minimum_window_tokens: int = Field(default=80, ge=1)
    pause_boundary_seconds: float = Field(default=1.2, ge=0)

    @model_validator(mode="after")
    def validate_window_limits(self) -> LongFormPolicy:
        if self.target_window_tokens > self.maximum_window_tokens:
            raise ValueError("target_window_tokens must not exceed maximum_window_tokens")
        if self.expected_schema_tokens + self.prompt_overhead_tokens >= self.model_context_tokens:
            raise ValueError("model context must leave room for transcript input")
        return self


class LongFormCallBudget(StrictModel):
    maximum_windows: int = Field(default=6, ge=1, le=32)
    maximum_primary_calls_per_window: int = Field(default=1, ge=1, le=3)
    maximum_repairs_per_window: int = Field(default=1, ge=0, le=2)
    maximum_total_model_calls: int = Field(default=12, ge=1)
    maximum_total_prompt_tokens: int = Field(default=120_000, ge=1_000)
    maximum_total_completion_tokens: int = Field(default=60_000, ge=1_000)
    maximum_processing_seconds: float = Field(default=600.0, gt=0)


class SegmentSlice(StrictModel):
    segment_id: str
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_slice(self) -> SegmentSlice:
        if self.end_char <= self.start_char:
            raise ValueError("segment slice must have positive length")
        return self


class TranscriptWindow(StrictModel):
    window_id: str
    ordinal: int = Field(ge=1)
    source_segment_ids: list[str] = Field(min_length=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    estimated_token_count: int = Field(ge=1)
    overlap_segment_ids: list[str] = Field(default_factory=list)
    boundary_reason: str
    planner_version: str = PLANNER_VERSION
    segment_slices: list[SegmentSlice] = Field(default_factory=list)


class WindowPlan(StrictModel):
    recording_id: str
    mode: LongFormMode
    planner_version: str = PLANNER_VERSION
    window_policy_version: str = WINDOW_POLICY_VERSION
    decision_reasons: list[str]
    segment_count: int = Field(ge=1)
    normalized_token_count: int = Field(ge=0)
    estimated_input_tokens: int = Field(ge=0)
    maximum_segment_tokens: int = Field(ge=0)
    windows: list[TranscriptWindow] = Field(min_length=1)


_TOKEN_RE = re.compile(r"[\w'-]+", re.UNICODE)


def estimate_tokens(text: str) -> int:
    """Conservative language-agnostic estimate without provider tokenization dependencies."""

    words = _TOKEN_RE.findall(text)
    non_space_chars = len(re.sub(r"\s+", "", text))
    return max(len(words), math.ceil(non_space_chars / 3.5)) if text else 0


def _stable_id(prefix: str, *parts: str) -> str:
    material = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(material).hexdigest()[:24]}"


class LongFormExtractionPlanner:
    def __init__(self, policy: LongFormPolicy | None = None) -> None:
        self.policy = policy or LongFormPolicy()

    def plan(self, transcript: TranscriptEnvelope) -> WindowPlan:
        segment_tokens = [estimate_tokens(segment.text) for segment in transcript.segments]
        normalized_tokens = sum(
            len(_TOKEN_RE.findall(segment.text)) for segment in transcript.segments
        )
        estimated_input = sum(segment_tokens) + self.policy.prompt_overhead_tokens
        maximum_segment_tokens = max(segment_tokens, default=0)
        reasons = self._decision_reasons(
            segment_count=len(transcript.segments),
            normalized_tokens=normalized_tokens,
            estimated_input=estimated_input,
            maximum_segment_tokens=maximum_segment_tokens,
        )
        mode = LongFormMode.WINDOWED if reasons else LongFormMode.SHORT
        if mode is LongFormMode.SHORT:
            windows = [
                self._window(
                    transcript=transcript,
                    ordinal=1,
                    segments=transcript.segments,
                    overlap_ids=[],
                    boundary_reason="short_path",
                )
            ]
        else:
            windows = self._windowed(transcript)
        return WindowPlan(
            recording_id=transcript.recording_id,
            mode=mode,
            decision_reasons=reasons or ["within_single_pass_limits"],
            segment_count=len(transcript.segments),
            normalized_token_count=normalized_tokens,
            estimated_input_tokens=estimated_input,
            maximum_segment_tokens=maximum_segment_tokens,
            windows=windows,
        )

    def _decision_reasons(
        self,
        *,
        segment_count: int,
        normalized_tokens: int,
        estimated_input: int,
        maximum_segment_tokens: int,
    ) -> list[str]:
        reasons: list[str] = []
        if segment_count > self.policy.segment_count_threshold:
            reasons.append("segment_count")
        if normalized_tokens > self.policy.normalized_token_threshold:
            reasons.append("normalized_tokens")
        if estimated_input > self.policy.estimated_input_token_threshold:
            reasons.append("estimated_input_tokens")
        if maximum_segment_tokens > self.policy.maximum_segment_tokens:
            reasons.append("oversized_segment")
        available = self.policy.model_context_tokens - self.policy.expected_schema_tokens
        if estimated_input > available:
            reasons.append("provider_context_limit")
        return reasons

    def _windowed(self, transcript: TranscriptEnvelope) -> list[TranscriptWindow]:
        expanded = self._expand_oversized_segments(transcript.segments)
        groups: list[list[RawSegment]] = []
        current: list[RawSegment] = []
        current_tokens = 0
        for segment in expanded:
            segment_tokens = estimate_tokens(segment.text)
            repeated_source_slice = bool(current) and current[-1].segment_id == segment.segment_id
            would_exceed = bool(current) and (
                current_tokens + segment_tokens > self.policy.maximum_window_tokens
                or len(current) >= self.policy.target_segments_per_window
                or repeated_source_slice
            )
            pause_boundary = bool(current) and (
                segment.start - current[-1].end >= self.policy.pause_boundary_seconds
                and current_tokens >= self.policy.minimum_window_tokens
            )
            if would_exceed or pause_boundary:
                groups.append(current)
                overlap = (
                    current[-self.policy.overlap_segments :]
                    if self.policy.overlap_segments and not repeated_source_slice
                    else []
                )
                current = list(overlap)
                current_tokens = sum(estimate_tokens(item.text) for item in current)
            current.append(segment)
            current_tokens += segment_tokens
        if current:
            groups.append(current)

        groups = self._coalesce_to_budget(groups)
        windows: list[TranscriptWindow] = []
        prior_ids: set[str] = set()
        for index, group in enumerate(groups, start=1):
            ids = [segment.segment_id for segment in group]
            overlap_ids = list(dict.fromkeys(item for item in ids if item in prior_ids))
            reason = (
                "final_segment" if index == len(groups) else "bounded_token_or_semantic_boundary"
            )
            windows.append(
                self._window(
                    transcript=transcript,
                    ordinal=index,
                    segments=group,
                    overlap_ids=overlap_ids,
                    boundary_reason=reason,
                )
            )
            prior_ids.update(ids)
        return windows

    def _expand_oversized_segments(self, segments: Iterable[RawSegment]) -> list[RawSegment]:
        expanded: list[RawSegment] = []
        for segment in segments:
            token_count = estimate_tokens(segment.text)
            if token_count <= self.policy.maximum_window_tokens:
                expanded.append(segment)
                continue
            slice_count = min(
                self.policy.maximum_windows,
                math.ceil(token_count / self.policy.target_window_tokens),
            )
            boundaries = _bounded_clause_slices(segment.text, slice_count)
            duration = segment.end - segment.start
            for start_char, end_char in boundaries:
                fraction_start = start_char / len(segment.text)
                fraction_end = end_char / len(segment.text)
                expanded.append(
                    RawSegment(
                        segment_id=segment.segment_id,
                        start=segment.start + duration * fraction_start,
                        end=segment.start + duration * fraction_end,
                        text=segment.text[start_char:end_char],
                        chunk_id=segment.chunk_id,
                    )
                )
        return expanded

    def _coalesce_to_budget(self, groups: list[list[RawSegment]]) -> list[list[RawSegment]]:
        groups = [list(group) for group in groups]
        while len(groups) > self.policy.maximum_windows:
            merge_index = min(
                range(len(groups) - 1),
                key=lambda index: (
                    sum(estimate_tokens(item.text) for item in groups[index])
                    + sum(estimate_tokens(item.text) for item in groups[index + 1])
                ),
            )
            merged = [*groups[merge_index], *groups[merge_index + 1]]
            groups[merge_index : merge_index + 2] = [list(_unique_segments(merged))]
        return groups

    def _window(
        self,
        *,
        transcript: TranscriptEnvelope,
        ordinal: int,
        segments: list[RawSegment],
        overlap_ids: list[str],
        boundary_reason: str,
    ) -> TranscriptWindow:
        original_by_id = {item.segment_id: item for item in transcript.segments}
        source_ids = list(dict.fromkeys(item.segment_id for item in segments))
        slices: list[SegmentSlice] = []
        for segment in segments:
            original = original_by_id[segment.segment_id]
            if segment.text != original.text:
                start_char = original.text.find(segment.text)
                if start_char >= 0:
                    slices.append(
                        SegmentSlice(
                            segment_id=segment.segment_id,
                            start_char=start_char,
                            end_char=start_char + len(segment.text),
                        )
                    )
        signature = ",".join(
            f"{item.segment_id}:{item.start:.3f}:{item.end:.3f}" for item in segments
        )
        return TranscriptWindow(
            window_id=_stable_id(
                "window",
                transcript.recording_id,
                self.policy.planner_version,
                str(ordinal),
                signature,
            ),
            ordinal=ordinal,
            source_segment_ids=source_ids,
            start_seconds=min(item.start for item in segments),
            end_seconds=max(item.end for item in segments),
            estimated_token_count=sum(estimate_tokens(item.text) for item in segments),
            overlap_segment_ids=overlap_ids,
            boundary_reason=boundary_reason,
            segment_slices=slices,
        )

    @staticmethod
    def materialize_window(
        transcript: TranscriptEnvelope,
        window: TranscriptWindow,
    ) -> TranscriptEnvelope:
        source = {item.segment_id: item for item in transcript.segments}
        slices = {item.segment_id: item for item in window.segment_slices}
        segments: list[RawSegment] = []
        for segment_id in window.source_segment_ids:
            original = source[segment_id]
            segment_slice = slices.get(segment_id)
            if segment_slice is None:
                segments.append(original)
                continue
            text = original.text[segment_slice.start_char : segment_slice.end_char]
            duration = original.end - original.start
            start_fraction = segment_slice.start_char / len(original.text)
            end_fraction = segment_slice.end_char / len(original.text)
            segments.append(
                original.model_copy(
                    update={
                        "start": original.start + duration * start_fraction,
                        "end": original.start + duration * end_fraction,
                        "text": text,
                    }
                )
            )
        return transcript.model_copy(
            update={
                "duration_seconds": max(item.end for item in segments),
                "full_text": " ".join(item.text for item in segments),
                "segments": segments,
            }
        )


def _unique_segments(segments: Iterable[RawSegment]) -> Iterable[RawSegment]:
    seen: set[tuple[str, str]] = set()
    for segment in segments:
        key = (segment.segment_id, segment.text)
        if key not in seen:
            seen.add(key)
            yield segment


def _bounded_clause_slices(text: str, slice_count: int) -> list[tuple[int, int]]:
    target = math.ceil(len(text) / slice_count)
    boundaries = [0]
    cursor = target
    while cursor < len(text):
        candidates = [
            index
            for index in range(max(boundaries[-1] + 1, cursor - 80), min(len(text), cursor + 80))
            if text[index] in ".!?;,:\n"
        ]
        boundary = (
            min(candidates, key=lambda value: abs(value - cursor)) + 1 if candidates else cursor
        )
        boundaries.append(boundary)
        cursor = boundary + target
    if boundaries[-1] < len(text):
        boundaries.append(len(text))
    return list(itertools.pairwise(boundaries))
