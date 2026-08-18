from __future__ import annotations

from typing import Any

from mura.deepseek.client import DeepSeekError, DeepSeekUsage
from mura.deepseek.focused_extraction import FocusedExtractionPass, merge_focused_pass
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import CleanerResult, RawSegment, ReadableSegment, TranscriptEnvelope
from mura.factual_support import FactualSupportStatus, evaluate_factual_support, sensitivity_level


class SequenceClient:
    def __init__(self, outputs: list[dict[str, Any] | Exception]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def request_json(self, **kwargs: Any) -> tuple[dict[str, Any], DeepSeekUsage]:
        self.calls.append(kwargs)
        output = self.outputs[len(self.calls) - 1]
        if isinstance(output, Exception):
            raise output
        return output, DeepSeekUsage(
            model="deepseek-test",
            finish_reason="stop",
            request_seconds=0.1,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )


def _transcript() -> TranscriptEnvelope:
    segments = [
        RawSegment(
            segment_id="seg_1",
            start=0,
            end=1,
            text="Анна — мать Бориса.",
        ),
        RawSegment(
            segment_id="seg_2",
            start=1,
            end=2,
            text="Вчера Борис переехал в Астану.",
        ),
        RawSegment(
            segment_id="seg_3",
            start=2,
            end=3,
            text="После переезда Борис позвонил Анне.",
        ),
    ]
    return TranscriptEnvelope(
        recording_id="rec_focused",
        duration_seconds=3,
        language_hints=["ru"],
        full_text=" ".join(item.text for item in segments),
        segments=segments,
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def _cleaned() -> CleanerResult:
    transcript = _transcript()
    return CleanerResult(
        readable_segments=[
            ReadableSegment(segment_id=item.segment_id, text=item.text)
            for item in transcript.segments
        ],
        full_readable_text=transcript.full_text,
    )


def _core_output() -> dict[str, Any]:
    return {
        "recording_id": "rec_focused",
        "speaker_id": "speaker_1",
        "speaker_name": "Айжан",
        "languages": ["ru"],
        "evidence_spans": [
            {
                "evidence_id": "anna",
                "segment_id": "seg_1",
                "text": "Анна",
                "source_layer": "raw_transcript",
                "start_char": None,
                "end_char": None,
                "evidence_class": "A_explicit",
                "purposes": ["identity"],
                "mention_ids": ["person_anna"],
            },
            {
                "evidence_id": "boris",
                "segment_id": "seg_1",
                "text": "Бориса",
                "source_layer": "raw_transcript",
                "start_char": None,
                "end_char": None,
                "evidence_class": "A_explicit",
                "purposes": ["identity"],
                "mention_ids": ["person_boris"],
            },
            {
                "evidence_id": "relation",
                "segment_id": "seg_1",
                "text": "Анна — мать Бориса",
                "source_layer": "raw_transcript",
                "start_char": None,
                "end_char": None,
                "evidence_class": "A_explicit",
                "purposes": ["claim"],
                "mention_ids": ["person_anna", "person_boris"],
            },
        ],
        "coreference_links": [],
        "people_mentions": [
            {
                "mention_id": "person_anna",
                "name": "Анна",
                "category": "family_member",
                "source_segment_ids": ["seg_1"],
                "evidence_ids": ["anna"],
                "confidence": 1.0,
            },
            {
                "mention_id": "person_boris",
                "name": "Борис",
                "category": "family_member",
                "source_segment_ids": ["seg_1", "seg_2", "seg_3"],
                "evidence_ids": ["boris"],
                "confidence": 1.0,
            },
        ],
        "relationship_claims": [
            {
                "relationship_id": "anna_boris",
                "relationship_type": "parent_child",
                "subject_mention_id": "person_anna",
                "subject_role": "parent",
                "object_mention_id": "person_boris",
                "object_role": "child",
                "source_segment_ids": ["seg_1"],
                "evidence_ids": ["relation"],
                "confidence": 1.0,
            }
        ],
    }


def _event_output(*, duplicate: bool = False) -> dict[str, Any]:
    events = [
        {
            "event_id": "move_1",
            "event_type": "move",
            "title": "Переезд Бориса",
            "participant_mention_ids": ["person_boris"],
            "location": "Астану",
            "description": "Борис переехал в Астану",
            "source_segment_ids": ["seg_2"],
            "evidence_ids": ["move"],
            "confidence": 1.0,
        }
    ]
    if duplicate:
        events.append({**events[0], "event_id": "move_duplicate"})
    return {
        "recording_id": "rec_focused",
        "speaker_id": "speaker_1",
        "speaker_name": "Айжан",
        "languages": ["ru"],
        "evidence_spans": [
            {
                "evidence_id": "move",
                "segment_id": "seg_2",
                "text": "Борис переехал в Астану",
                "source_layer": "raw_transcript",
                "start_char": None,
                "end_char": None,
                "evidence_class": "A_explicit",
                "purposes": ["claim"],
                "mention_ids": ["person_boris"],
            }
        ],
        "events": events,
        "descriptions": [],
    }


def _story_output() -> dict[str, Any]:
    return {
        "recording_id": "rec_focused",
        "speaker_id": "speaker_1",
        "speaker_name": "Айжан",
        "languages": ["ru"],
        "evidence_spans": [
            {
                "evidence_id": "call",
                "segment_id": "seg_3",
                "text": "Борис позвонил Анне",
                "source_layer": "raw_transcript",
                "start_char": None,
                "end_char": None,
                "evidence_class": "A_explicit",
                "purposes": ["claim"],
                "mention_ids": ["person_boris", "person_anna"],
            }
        ],
        "stories": [
            {
                "story_id": "story_call",
                "title": "Семейная история",
                "summary": "Борис позвонил Анне",
                "person_mention_ids": ["person_boris", "person_anna"],
                "event_ids": [],
                "privacy": "private",
                "sensitivity": "normal",
                "source_segment_ids": ["seg_3"],
                "evidence_ids": ["call"],
            }
        ],
        "unresolved_questions": [],
    }


def test_focused_extraction_runs_three_bounded_passes() -> None:
    client = SequenceClient([_core_output(), _event_output(), _story_output()])
    service = DeepSeekPipelineService(client, focused_extraction=True)  # type: ignore[arg-type]

    result, telemetry = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Айжан",
    )

    assert len(client.calls) == 3
    assert [item["payload"]["focused_pass"]["name"] for item in client.calls] == [
        "core",
        "events",
        "stories",
    ]
    assert [item.name for item in result.people_mentions] == ["Анна", "Борис"]
    assert [item.event_id for item in result.events] == ["move_1"]
    assert [item.story_id for item in result.stories] == ["story_call"]
    assert all("__" in item.evidence_id for item in result.evidence_spans)
    assert telemetry["extraction_mode"] == "focused"
    assert telemetry["focused_primary_calls"] == 3
    assert telemetry["focused_partial_failures"] == 0


def test_failed_event_pass_preserves_core_and_allows_story_pass() -> None:
    invalid = {**_event_output(), "people_mentions": []}
    client = SequenceClient([_core_output(), invalid, invalid, _story_output()])
    service = DeepSeekPipelineService(client, focused_extraction=True)  # type: ignore[arg-type]

    result, telemetry = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Айжан",
    )

    assert len(client.calls) == 4
    assert len(result.people_mentions) == 2
    assert result.events == []
    assert [item.story_id for item in result.stories] == ["story_call"]
    assert telemetry["focused_partial_failures"] == 1
    event_report = telemetry["focused_passes"][1]
    assert event_report["status"] == "failed"
    assert event_report["repair_attempted"] is True
    assert event_report["repair_succeeded"] is False


def test_duplicate_events_are_removed_by_semantic_key() -> None:
    base = {
        "recording_id": "rec_focused",
        "speaker_id": "speaker_1",
        "speaker_name": "Айжан",
        "languages": [],
        "evidence_spans": [],
        "events": [],
        "descriptions": [],
    }
    merged, metrics = merge_focused_pass(
        base,
        FocusedExtractionPass.EVENTS,
        _event_output(duplicate=True),
    )

    assert [item["event_id"] for item in merged["events"]] == ["move_1"]
    assert metrics.deduplicated_events == 1


def test_factual_support_rejects_role_reversal_and_added_motivation() -> None:
    role_reversal = evaluate_factual_support("Анна помогла Борис", "Борис помогла Анна")
    motivation = evaluate_factual_support(
        "Борис переехал в Астану ради работы",
        "Борис переехал в Астану",
    )

    assert role_reversal.status is FactualSupportStatus.ROLE_ORDER_CHANGED
    assert role_reversal.supported is False
    assert motivation.status in {
        FactualSupportStatus.ADDS_CAUSALITY,
        FactualSupportStatus.UNSUPPORTED,
    }
    assert motivation.supported is False


def test_provider_failure_in_optional_pass_is_fail_closed() -> None:
    client = SequenceClient(
        [_core_output(), DeepSeekError("provider unavailable"), _story_output()]
    )
    service = DeepSeekPipelineService(client, focused_extraction=True)  # type: ignore[arg-type]

    result, telemetry = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Айжан",
    )

    assert len(result.people_mentions) == 2
    assert result.events == []
    assert len(result.stories) == 1
    assert telemetry["focused_partial_failures"] == 1


def test_focused_repair_is_limited_to_failed_pass_and_preserves_prior_result() -> None:
    invalid_event = {**_event_output(), "people_mentions": []}
    client = SequenceClient([_core_output(), invalid_event, _event_output(), _story_output()])
    service = DeepSeekPipelineService(client, focused_extraction=True)  # type: ignore[arg-type]

    result, telemetry = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Айжан",
    )

    assert len(client.calls) == 4
    assert [item.event_id for item in result.events] == ["move_1"]
    assert [item.story_id for item in result.stories] == ["story_call"]
    event_report = telemetry["focused_passes"][1]
    assert event_report["repair_attempted"] is True
    assert event_report["repair_succeeded"] is True
    assert telemetry["focused_repair_calls"] == 1
    assert telemetry["focused_call_budget"] == 6


def test_duplicate_model_objects_are_reported_without_duplicate_acceptance() -> None:
    client = SequenceClient([_core_output(), _event_output(duplicate=True), _story_output()])
    service = DeepSeekPipelineService(client, focused_extraction=True)  # type: ignore[arg-type]

    result, telemetry = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Айжан",
    )

    assert [item.event_id for item in result.events] == ["move_1"]
    event_report = telemetry["focused_passes"][1]
    assert event_report["merge_metrics"]["deduplicated_events"] == 1
    assert event_report["issue_counts"]["duplicate_semantic_object"] == 1


def test_later_passes_receive_only_accepted_anchor_context() -> None:
    client = SequenceClient([_core_output(), _event_output(), _story_output()])
    service = DeepSeekPipelineService(client, focused_extraction=True)  # type: ignore[arg-type]

    service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Айжан",
    )

    event_payload = client.calls[1]["payload"]
    story_payload = client.calls[2]["payload"]
    assert set(event_payload["allowed_person_mention_ids"]) == {"person_anna", "person_boris"}
    assert "accepted_events" not in event_payload
    assert story_payload["allowed_event_ids"] == ["move_1"]
    assert {item["mention_id"] for item in story_payload["accepted_people"]} == {
        "person_anna",
        "person_boris",
    }


def test_story_sensitivity_uses_stable_reason_codes_and_token_boundaries() -> None:
    assert sensitivity_level("Это была сложная судьба семьи") == ("normal", [])
    assert sensitivity_level("Семья обсуждала суд и долг") == (
        "sensitive",
        ["legal_or_financial"],
    )
    level, reasons = sensitivity_level("Он пережил насилие")
    assert level == "highly_sensitive"
    assert reasons == ["violence_or_self_harm"]
    assert all("насилие" not in reason for reason in reasons)
