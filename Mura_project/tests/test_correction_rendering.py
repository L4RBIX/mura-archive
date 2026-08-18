from __future__ import annotations

import pytest

from mura.domain.models import (
    CleanerResult,
    CorrectionKind,
    DetectedCorrection,
    RawSegment,
    ReadableSegment,
    TranscriptEnvelope,
)
from mura.validation import ContractValidationError, validate_cleaner_result


def _transcript(text: str) -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_1",
        duration_seconds=10,
        full_text=text,
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text=text,
            )
        ],
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )


def test_adjacent_spelling_variant_is_asr_normalization() -> None:
    raw = _transcript("ал кенжеміз бекжат бекзат")
    result = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text="Ал кенжеміз Бекзат.")],
        detected_corrections=[
            DetectedCorrection(
                kind=CorrectionKind.ASR_NORMALIZATION,
                subject="Бекзат",
                original_value="бекжат",
                corrected_value="Бекзат",
                source_segment_ids=["seg_001"],
                explanation="The adjacent near-spelling variant is an ASR normalization.",
                confidence=1,
            )
        ],
        full_readable_text="Ал кенжеміз Бекзат.",
    )

    validate_cleaner_result(raw, result)


def test_explicit_kazakh_self_correction_may_render_only_final_value() -> None:
    raw = _transcript("жоқ 1942 емес 1943 болуы керек")
    result = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text="Жоқ, 1943 болуы керек.")],
        detected_corrections=[
            DetectedCorrection(
                kind=CorrectionKind.SPEAKER_SELF_CORRECTION,
                subject="birth_year",
                original_value="1942",
                corrected_value="1943",
                source_segment_ids=["seg_001"],
                explanation="The speaker explicitly replaces the earlier year.",
                confidence=1,
            )
        ],
        full_readable_text="Жоқ, 1943 болуы керек.",
    )

    validate_cleaner_result(raw, result)


def test_self_correction_without_explicit_cue_is_rejected() -> None:
    raw = _transcript("ал кенжеміз бекжат бекзат")
    result = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text="Ал кенжеміз Бекзат.")],
        detected_corrections=[
            DetectedCorrection(
                kind=CorrectionKind.SPEAKER_SELF_CORRECTION,
                subject="Бекзат",
                original_value="бекжат",
                corrected_value="Бекзат",
                source_segment_ids=["seg_001"],
                explanation="No explicit correction cue exists.",
                confidence=1,
            )
        ],
        full_readable_text="Ал кенжеміз Бекзат.",
    )

    with pytest.raises(ContractValidationError, match="without an explicit cue"):
        validate_cleaner_result(raw, result)


def test_correction_original_value_must_still_exist_in_raw_evidence() -> None:
    raw = _transcript("ал кенжеміз бекзат")
    result = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text="Ал кенжеміз Бекзат.")],
        detected_corrections=[
            DetectedCorrection(
                kind=CorrectionKind.ASR_NORMALIZATION,
                subject="Бекзат",
                original_value="бекжат",
                corrected_value="Бекзат",
                source_segment_ids=["seg_001"],
                explanation="Invented source evidence must be rejected.",
                confidence=1,
            )
        ],
        full_readable_text="Ал кенжеміз Бекзат.",
    )

    with pytest.raises(ContractValidationError, match="not present"):
        validate_cleaner_result(raw, result)
