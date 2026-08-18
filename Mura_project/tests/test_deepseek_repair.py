from __future__ import annotations

from typing import Any

from mura.deepseek.client import DeepSeekUsage
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import (
    CleanerResult,
    RawSegment,
    ReadableSegment,
    TranscriptEnvelope,
)


class FakeDeepSeekClient:
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
        return {
            "recording_id": "rec_1",
            "speaker_id": "speaker_1",
            "speaker_name": "Күләш",
            "languages": ["kk"],
            "people_mentions": [
                {
                    "mention_id": "mention_001",
                    "name": "Сапар",
                    "category": "family_member",
                    "source_segment_ids": ["seg_001"],
                    "confidence": 1.0,
                }
            ],
            "relationship_claims": [
                {
                    "relationship_id": "relationship_005",
                    "relationship_type": "parent_child",
                    "subject_mention_id": "mention_001",
                    "subject_role": "parent",
                    "object_mention_id": "mention_001",
                    "object_role": "child",
                    "source_segment_ids": ["seg_001"],
                    "confidence": 1.0,
                }
            ],
            "events": [],
            "descriptions": [],
            "stories": [],
            "unresolved_questions": [],
        }, usage


def test_extractor_quarantines_self_relationship_without_second_llm_call() -> None:
    transcript = TranscriptEnvelope(
        recording_id="rec_1",
        duration_seconds=12,
        full_text="Әкемнің аты Сапар.",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=12,
                text="әкемнің аты сапар",
            )
        ],
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )
    cleaned = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text="Әкемнің аты Сапар.")],
        full_readable_text="Әкемнің аты Сапар.",
    )
    client = FakeDeepSeekClient()
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.extract(
        transcript=transcript,
        cleaned=cleaned,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert client.calls == 1
    assert [person.name for person in result.people_mentions] == ["Сапар"]
    assert result.relationship_claims == []
    assert usage["repair_attempted"] is False
    assert usage["quarantined_items"] == 1
    issue = usage["extraction_issues"][0]
    assert issue["code"] == "object_schema_invalid"
    assert issue["object_id"] != "relationship_005"
    assert "relationship_005" not in repr(usage)
    assert "detail" not in issue
    assert usage["relationship_metrics"] == {
        "candidates": 1,
        "accepted": 0,
        "quarantined": 1,
        "acceptance_rate": 0.0,
    }


class RepairTriggeringClient:
    """First response carries a fatal top-level shape error; the retry response is valid."""

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
        base: dict[str, Any] = {
            "recording_id": "rec_1",
            "speaker_id": "speaker_1",
            "speaker_name": "Күләш",
            "languages": ["kk"],
            "relationship_claims": [],
            "events": [],
            "descriptions": [],
            "stories": [],
            "unresolved_questions": [],
        }
        if self.calls == 1:
            return {**base, "people_mentions": {"unexpected": "mapping"}}, usage
        return {
            **base,
            "people_mentions": [
                {
                    "mention_id": "mention_001",
                    "name": "Сапар",
                    "category": "family_member",
                    "source_segment_ids": ["seg_001"],
                    "confidence": 1.0,
                }
            ],
        }, usage


def _repair_fixture() -> tuple[TranscriptEnvelope, CleanerResult]:
    transcript = TranscriptEnvelope(
        recording_id="rec_1",
        duration_seconds=12,
        full_text="Әкемнің аты Сапар.",
        segments=[RawSegment(segment_id="seg_001", start=0, end=12, text="әкемнің аты сапар")],
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )
    cleaned = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text="Әкемнің аты Сапар.")],
        full_readable_text="Әкемнің аты Сапар.",
    )
    return transcript, cleaned


def test_window_repair_ceiling_of_zero_prevents_the_logical_repair_call() -> None:
    transcript, cleaned = _repair_fixture()
    client = RepairTriggeringClient()
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.extract_window(
        transcript=transcript,
        cleaned=cleaned,
        speaker_id="speaker_1",
        speaker_name="Күләш",
        maximum_repairs=0,
    )

    assert client.calls == 1
    assert usage["repair_attempted"] is False
    assert usage["model_calls"] == 1
    assert result.people_mentions == []


def test_default_window_budget_still_permits_one_logical_repair() -> None:
    transcript, cleaned = _repair_fixture()
    client = RepairTriggeringClient()
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.extract_window(
        transcript=transcript,
        cleaned=cleaned,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert client.calls == 2
    assert usage["repair_attempted"] is True
    assert usage["model_calls"] == 2
    assert [person.name for person in result.people_mentions] == ["Сапар"]
