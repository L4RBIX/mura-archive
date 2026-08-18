from __future__ import annotations

from typing import Any

from mura.deepseek.anchor_prompts import (
    ANCHOR_CONSTRAINED_EXTRACTION_REPAIR_SYSTEM_PROMPT,
    ANCHOR_CONSTRAINED_EXTRACTOR_SYSTEM_PROMPT,
)
from mura.deepseek.anchors import (
    LexicalAnnotationType,
    MentionAnchorKind,
    build_extraction_anchor_bundle,
)
from mura.deepseek.client import DeepSeekUsage
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import (
    CleanerResult,
    KnownPerson,
    RawSegment,
    ReadableSegment,
    TranscriptEnvelope,
)


def _transcript() -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_anchor",
        duration_seconds=10,
        language_hints=["kk"],
        full_text="менің ұлым ерлан",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text="менің ұлым ерлан",
            )
        ],
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )


def _cleaned() -> CleanerResult:
    return CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text="Менің ұлым Ерлан.")],
        full_readable_text="Менің ұлым Ерлан.",
    )


def _valid_extraction() -> dict[str, Any]:
    return {
        "recording_id": "rec_anchor",
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["kk"],
        "people_mentions": [
            {
                "mention_id": "mention_001",
                "name": "Ерлан",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            }
        ],
        "relationship_claims": [],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }


class SequenceClient:
    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        max_tokens: int,
        attempts: int = 3,
    ) -> tuple[dict[str, Any], DeepSeekUsage]:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "payload": payload,
                "max_tokens": max_tokens,
                "attempts": attempts,
            }
        )
        return self.outputs[len(self.calls) - 1], DeepSeekUsage(
            model="deepseek-v4-flash",
            finish_reason="stop",
            request_seconds=0.1,
        )


def test_anchor_bundle_contains_bounded_speaker_kinship_and_name_candidates() -> None:
    bundle = build_extraction_anchor_bundle(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_name="Күләш",
        known_people=[KnownPerson(person_id="person_kulash", canonical_name="Күләш")],
    )

    assert bundle.schema_version == "extraction-anchors-v1"
    assert bundle.allowed_segment_ids == ["seg_001"]
    assert any(
        anchor.anchor_kind is MentionAnchorKind.SPEAKER
        and anchor.surface == "Күләш"
        and anchor.known_person_id == "person_kulash"
        for anchor in bundle.mention_anchors
    )
    assert any(
        anchor.anchor_kind is MentionAnchorKind.NAME_CANDIDATE and anchor.surface == "Ерлан"
        for anchor in bundle.mention_anchors
    )
    assert any(
        annotation.annotation_type is LexicalAnnotationType.KINSHIP_LEXEME
        and annotation.surface == "ұлым"
        and annotation.segment_id == "seg_001"
        for annotation in bundle.lexical_annotations
    )


def test_extractor_receives_typed_anchor_contract_and_versioned_prompt() -> None:
    client = SequenceClient([_valid_extraction()])
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Күләш",
        known_people=[],
    )

    assert [person.name for person in result.people_mentions] == ["Ерлан"]
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["system_prompt"] == ANCHOR_CONSTRAINED_EXTRACTOR_SYSTEM_PROMPT
    anchor_contract = call["payload"]["anchor_contract"]
    assert anchor_contract["schema_version"] == "extraction-anchors-v1"
    assert anchor_contract["allowed_segment_ids"] == ["seg_001"]
    assert usage["repair_attempted"] is False
    assert usage["anchor_contract"]["allowed_segments"] == 1
    assert usage["anchor_contract"]["mention_anchors"] >= 2


def test_fatal_collection_shape_gets_one_bounded_repair_with_same_anchors() -> None:
    invalid = _valid_extraction()
    invalid["people_mentions"] = {"not": "a list"}
    client = SequenceClient([invalid, _valid_extraction()])
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Күләш",
        known_people=[],
    )

    assert [person.name for person in result.people_mentions] == ["Ерлан"]
    assert len(client.calls) == 2
    initial, repair = client.calls
    assert repair["system_prompt"] == ANCHOR_CONSTRAINED_EXTRACTION_REPAIR_SYSTEM_PROMPT
    assert repair["attempts"] == 2
    assert repair["payload"]["anchor_contract"] == initial["payload"]["anchor_contract"]
    assert repair["payload"]["previous_untrusted_output"] == invalid
    assert usage["repair_attempted"] is True
    assert usage["initial_usage"]["model"] == "deepseek-v4-flash"
    assert usage["relationship_metrics"]["candidates"] == 0


def test_isolated_invalid_object_is_quarantined_without_repair() -> None:
    invalid = _valid_extraction()
    invalid["people_mentions"] = [
        {
            "mention_id": "mention_bad",
            "name": "",
            "category": "family_member",
            "source_segment_ids": ["seg_001"],
            "confidence": 1.0,
        }
    ]
    client = SequenceClient([invalid])
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Күләш",
        known_people=[],
    )

    assert result.people_mentions == []
    assert len(client.calls) == 1
    assert usage["repair_attempted"] is False
    assert usage["quarantined_items"] == 1
    assert usage["extraction_issues"][0]["object_id"].startswith("object_")
    assert "mention_bad" not in str(usage["extraction_issues"])


def test_empty_valid_extraction_does_not_trigger_repair() -> None:
    empty = _valid_extraction()
    empty["people_mentions"] = []
    client = SequenceClient([empty])
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.extract(
        transcript=_transcript(),
        cleaned=_cleaned(),
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.people_mentions == []
    assert len(client.calls) == 1
    assert usage["repair_attempted"] is False
