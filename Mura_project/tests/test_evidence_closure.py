from __future__ import annotations

from typing import Any

import pytest

from mura.deepseek.client import DeepSeekUsage
from mura.deepseek.service import DeepSeekPipelineService
from mura.domain.models import (
    CleanerResult,
    CoreferenceStatus,
    EvidenceClass,
    ExtractionResult,
    PersonMention,
    RawSegment,
    ReadableSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    TranscriptEnvelope,
)
from mura.evidence import complete_relationship_evidence
from mura.validation import ContractValidationError, validate_extraction_result


def _transcript() -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_1",
        duration_seconds=20,
        full_text="Әкемнің аты Сапар. Оның інісі Нұрғали еді.",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=10,
                text="әкемнің аты сапар",
            ),
            RawSegment(
                segment_id="seg_002",
                start=10,
                end=20,
                text="оның інісі нұрғали еді",
            ),
        ],
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )


def _extraction(object_mention_id: str = "mention_nurgali") -> ExtractionResult:
    return ExtractionResult(
        recording_id="rec_1",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        people_mentions=[
            PersonMention(
                mention_id="mention_sapar",
                name="Сапар",
                category="family_member",
                source_segment_ids=["seg_001"],
                confidence=1,
            ),
            PersonMention(
                mention_id="mention_nurgali",
                name="Нұрғали",
                category="family_member",
                source_segment_ids=["seg_002"],
                confidence=1,
            ),
        ],
        relationship_claims=[
            RelationshipClaim(
                relationship_id="relationship_005",
                relationship_type=RelationshipType.SIBLING,
                subject_mention_id="mention_sapar",
                subject_role=RelationshipRole.OLDER_SIBLING,
                object_mention_id=object_mention_id,
                object_role=RelationshipRole.YOUNGER_SIBLING,
                source_segment_ids=["seg_002"],
                confidence=1,
            )
        ],
    )


def test_relationship_evidence_closure_resolves_unique_preceding_person() -> None:
    transcript = _transcript()
    completed, changed_count = complete_relationship_evidence(_extraction(), transcript)

    assert changed_count == 1
    relationship = completed.relationship_claims[0]
    assert relationship.source_segment_ids == ["seg_001", "seg_002"]
    assert relationship.evidence_ids
    assert len(relationship.coreference_link_ids) == 1
    link = completed.coreference_links[0]
    assert link.status is CoreferenceStatus.RESOLVED
    assert link.antecedent_mention_ids == ["mention_sapar"]
    validate_extraction_result(transcript, completed)


def test_relationship_evidence_closure_does_not_hide_unknown_endpoint() -> None:
    transcript = _transcript()
    malformed = _extraction(object_mention_id="mention_missing")

    completed, changed_count = complete_relationship_evidence(malformed, transcript)

    assert changed_count == 0
    with pytest.raises(ContractValidationError, match="unknown object mention"):
        validate_extraction_result(transcript, completed)


class EvidenceGapClient:
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
        return _extraction().model_dump(mode="json"), DeepSeekUsage(
            model="deepseek-v4-flash",
            finish_reason="stop",
            request_seconds=0.1,
        )


def test_extractor_accepts_unique_bounded_third_person_relationship() -> None:
    transcript = _transcript()
    cleaned = CleanerResult(
        readable_segments=[
            ReadableSegment(segment_id="seg_001", text="Әкемнің аты Сапар."),
            ReadableSegment(
                segment_id="seg_002",
                text="Оның інісі Нұрғали еді.",
            ),
        ],
        full_readable_text="Әкемнің аты Сапар. Оның інісі Нұрғали еді.",
    )
    client = EvidenceGapClient()
    service = DeepSeekPipelineService(client)  # type: ignore[arg-type]

    result, usage = service.extract(
        transcript=transcript,
        cleaned=cleaned,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert client.calls == 1
    assert usage["repair_attempted"] is False
    assert usage["evidence_closure_relationships"] == 1
    assert len(result.relationship_claims) == 1
    assert result.relationship_claims[0].evidence_class is EvidenceClass.D_CONTEXT_RESOLVED
    assert usage["relationship_metrics"] == {
        "candidates": 1,
        "accepted": 1,
        "quarantined": 0,
        "acceptance_rate": 1.0,
    }
    assert usage["extraction_issues"] == []
