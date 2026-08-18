from __future__ import annotations

from typing import Any

from mura.deepseek.client import DeepSeekUsage
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import RawSegment, TranscriptEnvelope
from mura.validation import validate_cleaner_result


class InvalidCleanerThenInvalidRepairClient:
    def __init__(self) -> None:
        self.calls = 0

    def request_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        max_tokens: int,
        attempts: int = 3,
    ) -> tuple[dict[str, Any], DeepSeekUsage]:
        del system_prompt, payload, max_tokens, attempts
        self.calls += 1
        usage = DeepSeekUsage(
            model="deepseek-v4-flash",
            finish_reason="stop",
            request_seconds=0.1,
        )
        invented_original = "\u0413\u0440\u0430\u0434"
        return {
            "readable_segments": [
                {
                    "segment_id": "seg_001",
                    "text": "We moved to the city of Almaty.",
                }
            ],
            "detected_corrections": [
                {
                    "kind": "asr_normalization",
                    "subject": None,
                    "original_value": invented_original,
                    "corrected_value": "city",
                    "source_segment_ids": ["seg_001"],
                    "explanation": "Unsupported model normalization.",
                    "confidence": 1.0,
                }
            ],
            "uncertain_fragments": [],
            "full_readable_text": "We moved to the city of Almaty.",
        }, usage


def test_cleaner_falls_back_to_raw_after_invalid_repair() -> None:
    raw_text = "We moved to Almaty."
    transcript = TranscriptEnvelope(
        recording_id="rec_1",
        duration_seconds=10,
        full_text=raw_text,
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text=raw_text,
            )
        ],
        asr_model="manual-text-fixture",
        asr_revision="v1",
        chunker_version="v1",
    )
    client = InvalidCleanerThenInvalidRepairClient()
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.clean(
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Kulash",
    )

    assert client.calls == 2
    assert [segment.text for segment in result.readable_segments] == [raw_text]
    assert result.full_readable_text == raw_text
    assert result.detected_corrections == []
    assert result.uncertain_fragments == []
    validate_cleaner_result(transcript, result)

    assert usage["model"] == "deepseek-v4-flash"
    assert usage["repair_attempted"] is True
    assert usage["fallback_used"] is True
    assert usage["fallback_strategy"] == "raw_transcript"
    assert usage["validation_issue_counts"] == {
        "cleaner_contract_invalid": 1,
        "cleaner_repair_failed": 1,
    }
    assert "initial_validation_error" not in usage
    assert "repair_validation_error" not in usage
    assert raw_text not in repr(usage)
