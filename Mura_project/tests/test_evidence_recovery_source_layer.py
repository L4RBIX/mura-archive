from __future__ import annotations

from copy import deepcopy
from typing import Any

from mura.deepseek.client import DeepSeekUsage
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import CleanerResult, RawSegment, ReadableSegment, TranscriptEnvelope
from mura.evidence_recovery import recover_evidence_offsets


def _transcript(text: str, *, recording_id: str = "rec_source_layer") -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id=recording_id,
        duration_seconds=10,
        language_hints=["ru", "kk"],
        full_text=text,
        segments=[RawSegment(segment_id="seg_001", start=0, end=10, text=text)],
        asr_model="manual-text-fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def _candidate(
    *,
    text: str,
    start_char: int | None,
    end_char: int | None,
    source_layer: str | None = "readable_transcript",
) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "evidence_id": "evidence_1",
        "segment_id": "seg_001",
        "text": text,
        "start_char": start_char,
        "end_char": end_char,
        "evidence_class": "A_explicit",
        "purposes": ["claim"],
        "mention_ids": [],
        "coreference_link_ids": [],
        "derived_from_evidence_ids": [],
        "confidence": 1.0,
    }
    if source_layer is not None:
        candidate["source_layer"] = source_layer
    return candidate


def _recover_one(
    *,
    transcript: TranscriptEnvelope,
    candidate: dict[str, Any],
    cleaned: CleanerResult | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    recovered, metrics = recover_evidence_offsets(
        raw={"evidence_spans": [candidate]},
        transcript=transcript,
        cleaned=cleaned,
    )
    recovered_candidate = recovered["evidence_spans"][0]
    assert isinstance(recovered_candidate, dict)
    return recovered_candidate, metrics.to_dict()


def _assert_raw_recovery_counters_are_zero(metrics: dict[str, int]) -> None:
    assert metrics["repaired_evidence_offsets"] == 0
    assert metrics["exact_offsets_accepted"] == 0
    assert metrics["unique_match_repaired"] == 0
    assert metrics["nearest_match_repaired"] == 0
    assert metrics["ambiguous_offsets_removed"] == 0
    assert metrics["missing_text_quarantined"] == 0
    assert metrics["unknown_segment_quarantined"] == 0


def test_readable_candidate_recovers_only_against_readable_segment() -> None:
    transcript = _transcript("Исходный текст сегмента")
    readable_text = "Исправленный текст"
    cleaned = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text=readable_text)],
        full_readable_text=readable_text,
    )
    candidate = _candidate(
        text=readable_text,
        start_char=3,
        end_char=3 + len(readable_text),
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate, cleaned=cleaned)

    assert recovered["start_char"] == 0
    assert recovered["end_char"] == len(readable_text)
    assert metrics["recovered"] == 1
    assert metrics["wrong_source_layer"] == 0
    assert metrics["non_raw_evidence_skipped"] == 0


def test_readable_candidate_is_not_repositioned_using_raw_match() -> None:
    raw_text = "Префикс Күләш суффикс"
    readable_text = "Күләш в начале"
    transcript = _transcript(raw_text)
    cleaned = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text=readable_text)],
        full_readable_text=readable_text,
    )
    raw_position = raw_text.index("Күләш")
    candidate = _candidate(
        text="Күләш",
        start_char=0,
        end_char=len("Күләш"),
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate, cleaned=cleaned)

    assert raw_position != candidate["start_char"]
    assert recovered == candidate
    assert metrics["already_valid"] == 1
    assert metrics["recovered"] == 0
    assert metrics["wrong_source_layer"] == 0


def test_readable_text_absent_from_raw_is_valid_when_present_in_readable_layer() -> None:
    transcript = _transcript("Сырой текст")
    readable_text = "Читаемый текст"
    cleaned = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text=readable_text)],
        full_readable_text=readable_text,
    )
    candidate = _candidate(
        text=readable_text,
        start_char=0,
        end_char=len(readable_text),
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate, cleaned=cleaned)

    assert recovered == candidate
    assert metrics["already_valid"] == 1
    assert metrics["missing"] == 0
    assert metrics["wrong_source_layer"] == 0


def test_missing_source_layer_uses_raw_transcript_default() -> None:
    text = "Меня зовут Күләш"
    transcript = _transcript(text)
    candidate = _candidate(
        text=text,
        start_char=0,
        end_char=len(text) + 1,
        source_layer=None,
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert "source_layer" not in recovered
    assert recovered["start_char"] == 0
    assert recovered["end_char"] == len(text)
    assert metrics["unique_match_repaired"] == 1
    assert metrics["repaired_evidence_offsets"] == 1
    assert metrics["non_raw_evidence_skipped"] == 0


def test_explicit_raw_off_by_one_recovery_is_unchanged() -> None:
    text = "Нұржан — мой младший сын"
    transcript = _transcript(text)
    candidate = _candidate(
        text=text,
        start_char=0,
        end_char=len(text) + 1,
        source_layer="raw_transcript",
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert recovered["start_char"] == 0
    assert recovered["end_char"] == len(text)
    assert metrics["unique_match_repaired"] == 1
    assert metrics["non_raw_evidence_skipped"] == 0


def test_readable_recovery_is_idempotent_and_side_effect_free() -> None:
    transcript = _transcript("Префикс Күләш суффикс")
    readable_text = "Күләш в начале"
    cleaned = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text=readable_text)],
        full_readable_text=readable_text,
    )
    candidate = _candidate(
        text="Күләш",
        start_char=0,
        end_char=len("Күләш"),
    )
    raw = {"evidence_spans": [candidate]}
    original = deepcopy(raw)

    first, first_metrics = recover_evidence_offsets(raw=raw, transcript=transcript, cleaned=cleaned)
    second, second_metrics = recover_evidence_offsets(
        raw=first, transcript=transcript, cleaned=cleaned
    )

    assert raw == original
    assert first == second == original
    assert first_metrics.to_dict() == second_metrics.to_dict()
    assert first_metrics.already_valid == 1
    assert first_metrics.repaired_evidence_offsets == 0


class _SingleExtractionClient:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
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
        return self.raw, DeepSeekUsage(
            model="deepseek-v4-flash",
            finish_reason="stop",
            request_seconds=0.1,
        )


def test_extractor_usage_counts_non_raw_skip_once_without_sensitive_text() -> None:
    raw_text = "Сырой семейный текст"
    readable_text = "Исправленный семейный текст"
    transcript = _transcript(raw_text, recording_id="rec_source_layer_telemetry")
    candidate = _candidate(
        text=readable_text,
        start_char=0,
        end_char=len(readable_text),
    )
    raw: dict[str, Any] = {
        "recording_id": transcript.recording_id,
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["ru"],
        "provenance_activities": [],
        "evidence_spans": [candidate],
        "coreference_links": [],
        "conflict_sets": [],
        "people_mentions": [],
        "relationship_claims": [],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }
    cleaned = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text=readable_text)],
        full_readable_text=readable_text,
    )
    client = _SingleExtractionClient(raw)
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    _, usage = service.extract(
        transcript=transcript,
        cleaned=cleaned,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    recovery_usage = usage["evidence_offset_recovery"]
    assert client.calls == 1
    assert recovery_usage["non_raw_evidence_skipped"] == 0
    assert recovery_usage["already_valid"] == 1
    assert recovery_usage["wrong_source_layer"] == 0
    assert recovery_usage["missing_text_quarantined"] == 0
    assert recovery_usage["repaired_evidence_offsets"] == 0
    assert all(type(value) is int for value in recovery_usage.values())
    assert raw_text not in str(recovery_usage)
    assert readable_text not in str(recovery_usage)
    assert "Күләш" not in str(recovery_usage)
