from __future__ import annotations

from typing import Any

from mura.deepseek import DeepSeekPipelineService
from mura.deepseek.client import DeepSeekUsage
from mura.deepseek.discourse_telemetry import discourse_link_counters
from mura.domain.models import (
    CleanerResult,
    CoreferenceLink,
    CoreferenceMethod,
    CoreferenceStatus,
    ExtractionResult,
    GrammaticalNumber,
    RawSegment,
    ReadableSegment,
    TranscriptEnvelope,
)


class SequenceClient:
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
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
        return self.output, DeepSeekUsage(
            model="deepseek-v4-flash",
            finish_reason="stop",
            request_seconds=0.1,
        )


def _transcript() -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_coref_metrics",
        duration_seconds=20,
        language_hints=["ru"],
        full_text="Ермек уехал. У него жена Сауле.",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text="Ермек уехал.",
            ),
            RawSegment(
                segment_id="seg_002",
                start=10,
                end=20,
                text="У него жена Сауле.",
            ),
        ],
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def _cleaned() -> CleanerResult:
    return CleanerResult(
        readable_segments=[
            ReadableSegment(segment_id="seg_001", text="Ермек уехал."),
            ReadableSegment(segment_id="seg_002", text="У него жена Сауле."),
        ],
        full_readable_text="Ермек уехал. У него жена Сауле.",
    )


def _raw_extraction() -> dict[str, Any]:
    return {
        "recording_id": "rec_coref_metrics",
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["ru"],
        "people_mentions": [
            {
                "mention_id": "ermek",
                "name": "Ермек",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "saule",
                "name": "Сауле",
                "category": "family_member",
                "source_segment_ids": ["seg_002"],
                "confidence": 1.0,
            },
        ],
        "relationship_claims": [
            {
                "relationship_id": "relationship_spouse",
                "relationship_type": "spouse",
                "subject_mention_id": "ermek",
                "subject_role": "spouse",
                "object_mention_id": "saule",
                "object_role": "spouse",
                "source_segment_ids": ["seg_002"],
                "confidence": 1.0,
            }
        ],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }


def test_public_service_exposes_integer_only_coreference_metrics_once() -> None:
    client = SequenceClient(_raw_extraction())
    service = DeepSeekPipelineService(client)

    result, usage = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert client.calls == 1
    assert len(result.coreference_links) == 1
    assert usage["coreference_metrics"] == {
        "singular_coreference_resolved": 1,
        "plural_coreference_resolved": 0,
        "ambiguous_coreference_rejected": 0,
        "unresolved_coreference_rejected": 0,
    }
    assert all(isinstance(value, int) for value in usage["coreference_metrics"].values())
    assert "Ермек" not in repr(usage["coreference_metrics"])
    assert "Сауле" not in repr(usage["coreference_metrics"])


def test_discourse_counters_cover_final_link_states_without_text() -> None:
    links = [
        CoreferenceLink(
            coreference_id="singular",
            anaphor_text="hidden singular",
            source_segment_ids=["seg_001"],
            evidence_ids=["evidence_singular"],
            status=CoreferenceStatus.RESOLVED,
            method=CoreferenceMethod.DETERMINISTIC_DISCOURSE,
            grammatical_number=GrammaticalNumber.SINGULAR,
            antecedent_mention_ids=["person_1"],
            candidate_mention_ids=["person_1"],
            confidence=1.0,
            reason="fixture",
        ),
        CoreferenceLink(
            coreference_id="plural",
            anaphor_text="hidden plural",
            source_segment_ids=["seg_001"],
            evidence_ids=["evidence_plural"],
            status=CoreferenceStatus.RESOLVED,
            method=CoreferenceMethod.DETERMINISTIC_DISCOURSE,
            grammatical_number=GrammaticalNumber.PLURAL,
            antecedent_mention_ids=["person_1", "person_2"],
            candidate_mention_ids=["person_1", "person_2"],
            confidence=1.0,
            reason="fixture",
        ),
        CoreferenceLink(
            coreference_id="ambiguous",
            anaphor_text="hidden ambiguous",
            source_segment_ids=["seg_001"],
            evidence_ids=["evidence_ambiguous"],
            status=CoreferenceStatus.AMBIGUOUS,
            method=CoreferenceMethod.DETERMINISTIC_DISCOURSE,
            grammatical_number=GrammaticalNumber.SINGULAR,
            candidate_mention_ids=["person_1", "person_2"],
            confidence=0.5,
            reason="fixture",
        ),
    ]
    result = ExtractionResult(
        recording_id="rec_metrics",
        speaker_id="speaker_1",
        speaker_name="Narrator",
        coreference_links=links,
    )

    counters = discourse_link_counters(result)

    assert counters == {
        "singular_coreference_resolved": 1,
        "plural_coreference_resolved": 1,
        "ambiguous_coreference_rejected": 1,
        "unresolved_coreference_rejected": 0,
    }
    assert all(isinstance(value, int) for value in counters.values())
    assert "hidden" not in repr(counters)
