from __future__ import annotations

from typing import Any

from mura.deepseek.client import DeepSeekUsage
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import RawSegment, TranscriptEnvelope


class FakeCleanerClient:
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
        if self.calls == 1:
            return {
                "readable_segments": [
                    {"segment_id": "seg_001", "text": "Она была и любила читать."}
                ],
                "detected_corrections": [],
                "uncertain_fragments": [
                    {
                        "source_segment_ids": ["seg_001"],
                        "raw_text": "ичи",
                        "possible_interpretation": None,
                        "reason": "unclear token",
                    }
                ],
                "full_readable_text": "Она была и любила читать.",
            }, usage

        return {
            "readable_segments": [
                {"segment_id": "seg_001", "text": "Она была ичи и любила читать."}
            ],
            "detected_corrections": [],
            "uncertain_fragments": [
                {
                    "source_segment_ids": ["seg_001"],
                    "raw_text": "ичи",
                    "possible_interpretation": None,
                    "reason": "unclear token",
                }
            ],
            "full_readable_text": "Она была ичи и любила читать.",
        }, usage


def test_cleaner_repairs_removed_uncertain_span_once() -> None:
    transcript = TranscriptEnvelope(
        recording_id="rec_1",
        duration_seconds=10,
        full_text="она была ичи и любила читать",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text="она была ичи и любила читать",
            )
        ],
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )
    client = FakeCleanerClient()
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.clean(
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert client.calls == 2
    assert "ичи" in result.readable_segments[0].text
    assert usage["repair_attempted"] is True
    assert usage["validation_issue_counts"] == {"cleaner_contract_invalid": 1}
    assert "initial_validation_error" not in usage
    assert "ичи" not in repr(usage)
