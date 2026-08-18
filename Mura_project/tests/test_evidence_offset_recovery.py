from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from mura.deepseek.client import DeepSeekUsage
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import (
    CleanerResult,
    EvidenceSpan,
    RawSegment,
    ReadableSegment,
    TranscriptEnvelope,
)
from mura.evidence_recovery import recover_evidence_offsets
from mura.extraction_sanitizer import sanitize_extraction_output


def _transcript(text: str, *, recording_id: str = "rec_1") -> TranscriptEnvelope:
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


def _evidence_candidate(
    *,
    text: str,
    start_char: int | None,
    end_char: int | None,
    evidence_id: str = "evidence_1",
    segment_id: str = "seg_001",
    purposes: list[str] | None = None,
    mention_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "segment_id": segment_id,
        "text": text,
        "source_layer": "raw_transcript",
        "start_char": start_char,
        "end_char": end_char,
        "evidence_class": "A_explicit",
        "purposes": purposes or ["claim"],
        "mention_ids": mention_ids or [],
        "coreference_link_ids": [],
        "derived_from_evidence_ids": [],
        "confidence": 1.0,
    }


def _recover_one(
    *,
    transcript: TranscriptEnvelope,
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    recovered, metrics = recover_evidence_offsets(
        raw={"evidence_spans": [candidate]},
        transcript=transcript,
    )
    recovered_candidate = recovered["evidence_spans"][0]
    assert isinstance(recovered_candidate, dict)
    return recovered_candidate, metrics.to_dict()


def _empty_raw(
    *,
    transcript: TranscriptEnvelope,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "recording_id": transcript.recording_id,
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["ru", "kk"],
        "provenance_activities": [],
        "evidence_spans": evidence,
        "coreference_links": [],
        "conflict_sets": [],
        "people_mentions": [],
        "relationship_claims": [],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }


def _person_raw(
    transcript: TranscriptEnvelope,
    *,
    evidence_end: int,
) -> dict[str, Any]:
    start = transcript.segments[0].text.index("Күләш")
    evidence = _evidence_candidate(
        text="Күләш",
        start_char=start,
        end_char=evidence_end,
        purposes=["identity"],
        mention_ids=["mention_kulash"],
    )
    raw = _empty_raw(transcript=transcript, evidence=[evidence])
    raw["people_mentions"] = [
        {
            "mention_id": "mention_kulash",
            "name": "Күләш",
            "category": "family_member",
            "relation_to_speaker": "self",
            "source_segment_ids": ["seg_001"],
            "evidence_ids": ["evidence_1"],
            "confidence": 1.0,
        }
    ]
    return raw


def test_valid_offsets_remain_unchanged() -> None:
    transcript = _transcript("Меня зовут Күләш")
    start = transcript.segments[0].text.index("Күләш")
    candidate = _evidence_candidate(
        text="Күләш",
        start_char=start,
        end_char=start + len("Күләш"),
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert recovered == candidate
    assert metrics["exact_offsets_accepted"] == 1
    assert metrics["repaired_evidence_offsets"] == 0


def test_off_by_one_end_is_repaired() -> None:
    text = "Меня зовут Күләш Сапаровна"
    transcript = _transcript(text)
    candidate = _evidence_candidate(text=text, start_char=0, end_char=len(text) + 1)

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert recovered["start_char"] == 0
    assert recovered["end_char"] == len(text)
    assert metrics["unique_match_repaired"] == 1
    assert metrics["repaired_evidence_offsets"] == 1


def test_off_by_one_start_is_repaired() -> None:
    text = "Меня зовут Күләш"
    transcript = _transcript(text)
    actual_start = text.index("Күләш")
    candidate = _evidence_candidate(
        text="Күләш",
        start_char=actual_start - 1,
        end_char=actual_start - 1 + len("Күләш"),
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert recovered["start_char"] == actual_start
    assert recovered["end_char"] == actual_start + len("Күләш")
    assert metrics["unique_match_repaired"] == 1


def test_completely_wrong_unique_position_is_repaired() -> None:
    text = "Меня зовут Күләш Сапаровна"
    transcript = _transcript(text)
    actual_start = text.index("Сапаровна")
    candidate = _evidence_candidate(
        text="Сапаровна",
        start_char=0,
        end_char=len("Сапаровна"),
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert recovered["start_char"] == actual_start
    assert recovered["end_char"] == actual_start + len("Сапаровна")
    assert metrics["unique_match_repaired"] == 1


def test_kazakh_unicode_uses_python_code_point_offsets() -> None:
    text = "Нұржан — мой младший сын"
    transcript = _transcript(text)
    candidate = _evidence_candidate(
        text=text,
        start_char=0,
        end_char=len(text.encode("utf-8")),
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert recovered["end_char"] == len(text)
    assert recovered["end_char"] != len(text.encode("utf-8"))
    assert metrics["unique_match_repaired"] == 1


def test_long_dash_and_punctuation_are_matched_exactly() -> None:
    text = "Айгүл — моя младшая сестра"
    transcript = _transcript(text)
    candidate = _evidence_candidate(text=text, start_char=0, end_char=len(text) + 1)

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert recovered["start_char"] == 0
    assert recovered["end_char"] == len(text)
    assert metrics["unique_match_repaired"] == 1


def test_duplicate_text_never_uses_untrusted_proposed_start() -> None:
    text = "Күләш сказала. Потом Күләш улыбнулась."
    transcript = _transcript(text)
    second_start = text.rindex("Күләш")
    candidate = _evidence_candidate(
        text="Күләш",
        start_char=second_start + 1,
        end_char=second_start + 1 + len("Күләш"),
    )

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert recovered["start_char"] is None
    assert recovered["end_char"] is None
    assert metrics["ambiguous"] == 1
    assert metrics["nearest_match_repaired"] == 0


def test_duplicate_text_with_equal_ambiguity_preserves_evidence_without_offsets() -> None:
    text = "abcXXXXXabc"
    transcript = _transcript(text)
    candidate = _evidence_candidate(text="abc", start_char=4, end_char=7)

    recovered, metrics = _recover_one(transcript=transcript, candidate=candidate)

    assert recovered["evidence_id"] == "evidence_1"
    assert recovered["text"] == "abc"
    assert recovered["start_char"] is None
    assert recovered["end_char"] is None
    assert metrics["ambiguous_offsets_removed"] == 1
    assert metrics["repaired_evidence_offsets"] == 0


def test_text_absent_from_raw_segment_remains_quarantined() -> None:
    transcript = _transcript("Мы переехали в Алматы.")
    candidate = _evidence_candidate(text="Град", start_char=None, end_char=None)
    raw = _empty_raw(transcript=transcript, evidence=[candidate])

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.evidence_spans == []
    issue = next(item for item in issues if item["object_id"] == "evidence_1")
    assert issue["stage"] == "evidence_recovery"
    assert issue["code"] == "evidence_text_not_in_source"


def test_unknown_segment_id_remains_quarantined() -> None:
    transcript = _transcript("Меня зовут Күләш")
    candidate = _evidence_candidate(
        text="Күләш",
        start_char=0,
        end_char=len("Күләш"),
        segment_id="seg_missing",
    )
    raw = _empty_raw(transcript=transcript, evidence=[candidate])

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.evidence_spans == []
    issue = next(item for item in issues if item["object_id"] == "evidence_1")
    assert issue["stage"] == "evidence_recovery"
    assert issue["code"] == "evidence_unknown_segment"


def test_repaired_evidence_preserves_downstream_person_reference() -> None:
    transcript = _transcript("Меня зовут Күләш")
    start = transcript.segments[0].text.index("Күләш")
    raw = _person_raw(transcript, evidence_end=start + len("Күләш") + 1)

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.evidence_spans[0].evidence_id == "evidence_1"
    assert result.evidence_spans[0].start_char == start
    assert result.people_mentions[0].evidence_ids == ["evidence_1"]
    assert not any(
        "unknown or out-of-scope evidence IDs were removed" in issue["detail"] for issue in issues
    )


def test_repaired_evidence_preserves_downstream_relationship_reference() -> None:
    text = "Мою младшую дочь зовут Айгуль."
    transcript = _transcript(text, recording_id="rec_relationship")
    evidence_id = "evidence_relationship"
    evidence = _evidence_candidate(
        evidence_id=evidence_id,
        text=text,
        start_char=0,
        end_char=len(text) + 1,
        mention_ids=["mention_kulash", "mention_aigul"],
    )
    raw = _empty_raw(transcript=transcript, evidence=[evidence])
    raw["people_mentions"] = [
        {
            "mention_id": "mention_kulash",
            "name": "Күләш",
            "category": "family_member",
            "relation_to_speaker": "self",
            "source_segment_ids": ["seg_001"],
            "evidence_ids": [evidence_id],
            "confidence": 1.0,
        },
        {
            "mention_id": "mention_aigul",
            "name": "Айгуль",
            "category": "family_member",
            "relation_to_speaker": "daughter",
            "source_segment_ids": ["seg_001"],
            "evidence_ids": [evidence_id],
            "confidence": 1.0,
        },
    ]
    raw["relationship_claims"] = [
        {
            "relationship_id": "relationship_parent",
            "relationship_type": "parent_child",
            "subject_mention_id": "mention_kulash",
            "subject_role": "parent",
            "object_mention_id": "mention_aigul",
            "object_role": "child",
            "source_segment_ids": ["seg_001"],
            "evidence_ids": [evidence_id],
            "confidence": 1.0,
        }
    ]

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert [item.evidence_id for item in result.evidence_spans] == [evidence_id]
    assert result.relationship_claims[0].evidence_ids == [evidence_id]
    assert not any(
        "unknown or out-of-scope evidence IDs were removed" in issue["detail"] for issue in issues
    )


def test_evidence_span_length_validator_remains_strict() -> None:
    candidate = _evidence_candidate(text="Күләш", start_char=0, end_char=6)

    with pytest.raises(
        ValidationError,
        match="evidence offsets must span exactly evidence text length",
    ):
        EvidenceSpan.model_validate(candidate)


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


def test_extractor_usage_reports_recovery_without_sensitive_text() -> None:
    transcript = _transcript("Меня зовут Күләш", recording_id="rec_telemetry")
    start = transcript.segments[0].text.index("Күләш")
    raw = _person_raw(transcript, evidence_end=start + len("Күләш") + 1)
    cleaned = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text=transcript.full_text)],
        full_readable_text=transcript.full_text,
    )
    client = _SingleExtractionClient(raw)
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.extract(
        transcript=transcript,
        cleaned=cleaned,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert client.calls == 1
    assert result.people_mentions[0].evidence_ids == ["evidence_1"]
    assert usage["repair_attempted"] is False
    assert usage["repaired_evidence_offsets"] == 1
    assert usage["evidence_offset_recovery"]["unique_match_repaired"] == 1
    assert "Күләш" not in str(usage["evidence_offset_recovery"])
