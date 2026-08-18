from __future__ import annotations

import pytest
from pydantic import ValidationError

from mura.claim_model import is_auto_acceptable_evidence_class
from mura.domain.models import (
    CoreferenceLink,
    CoreferenceMethod,
    CoreferenceStatus,
    EvidenceClass,
    GrammaticalNumber,
    NameVariant,
    NameVariantType,
    RawSegment,
    TranscriptEnvelope,
)
from mura.extraction_sanitizer import sanitize_extraction_output
from mura.validation import validate_extraction_result


def _transcript(*segments: tuple[str, str]) -> TranscriptEnvelope:
    raw_segments = [
        RawSegment(
            segment_id=segment_id,
            start=index * 10,
            end=(index + 1) * 10,
            text=text,
        )
        for index, (segment_id, text) in enumerate(segments)
    ]
    return TranscriptEnvelope(
        recording_id="rec_claim_v2",
        duration_seconds=float(len(raw_segments) * 10),
        full_text=" ".join(segment.text for segment in raw_segments),
        segments=raw_segments,
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )


def _explicit_relationship_raw() -> dict[str, object]:
    return {
        "recording_id": "rec_claim_v2",
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["kk"],
        "people_mentions": [
            {
                "mention_id": "mention_erlan",
                "name": "Ерлан",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_dinara",
                "name": "Динара",
                "category": "family_member",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            },
        ],
        "relationship_claims": [
            {
                "relationship_id": "relationship_spouse",
                "relationship_type": "spouse",
                "subject_mention_id": "mention_erlan",
                "subject_role": "spouse",
                "object_mention_id": "mention_dinara",
                "object_role": "spouse",
                "source_segment_ids": ["seg_001"],
                "confidence": 1.0,
            }
        ],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }


def test_legacy_candidate_is_materialized_as_complete_v2_claim_bundle() -> None:
    transcript = _transcript(("seg_001", "Ерланның әйелі Динара."))

    result, issues, closure_count = sanitize_extraction_output(
        raw=_explicit_relationship_raw(),
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert issues == []
    assert closure_count == 0
    assert result.schema_version == "extraction-v2"
    assert [activity.stage.value for activity in result.provenance_activities] == [
        "asr",
        "extractor",
        "sanitizer",
    ]
    assert len(result.evidence_spans) == 3

    relationship = result.relationship_claims[0]
    assert relationship.evidence_class is EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT
    assert relationship.evidence_ids
    assert relationship.provenance is not None
    assert relationship.provenance.recording_id == transcript.recording_id
    assert relationship.provenance.evidence_ids == relationship.evidence_ids
    assert relationship.provenance.pipeline_versions["domain_schema"] == "domain-v5-identity-safety"

    for person in result.people_mentions:
        assert person.evidence_ids
        assert person.provenance is not None
        assert any(
            variant.variant_type is NameVariantType.PRIMARY and variant.surface == person.name
            for variant in person.name_variants
        )

    validate_extraction_result(transcript, result)


def test_invalid_model_evidence_is_quarantined_and_replaced() -> None:
    transcript = _transcript(("seg_001", "Ерланның әйелі Динара."))
    raw = _explicit_relationship_raw()
    raw["evidence_spans"] = [
        {
            "evidence_id": "evidence_invented",
            "segment_id": "seg_001",
            "text": "мәтінде жоқ",
            "source_layer": "raw_transcript",
            "evidence_class": "A_explicit",
            "purposes": ["identity"],
            "mention_ids": ["mention_erlan"],
            "confidence": 1.0,
        }
    ]
    people = raw["people_mentions"]
    assert isinstance(people, list)
    assert isinstance(people[0], dict)
    people[0]["evidence_ids"] = ["evidence_invented"]

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert "evidence_invented" not in {item.evidence_id for item in result.evidence_spans}
    evidence_issue = next(item for item in issues if item["object_id"] == "evidence_invented")
    assert evidence_issue["stage"] == "evidence_recovery"
    assert evidence_issue["code"] == "evidence_text_not_in_source"
    assert result.people_mentions[0].evidence_ids
    validate_extraction_result(transcript, result)


def test_deterministic_coreference_replaces_model_only_authorization() -> None:
    transcript = _transcript(
        ("seg_001", "Ерлан инженер."),
        ("seg_002", "Оның ұлы Нұрлан."),
    )
    raw: dict[str, object] = {
        "schema_version": "extraction-v2",
        "recording_id": "rec_claim_v2",
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": ["kk"],
        "evidence_spans": [
            {
                "evidence_id": "evidence_pronoun",
                "segment_id": "seg_002",
                "text": "Оның",
                "source_layer": "raw_transcript",
                "evidence_class": "D_context_resolved",
                "purposes": ["coreference"],
                "mention_ids": ["mention_erlan"],
                "confidence": 0.8,
            }
        ],
        "coreference_links": [
            {
                "coreference_id": "coreference_001",
                "anaphor_text": "Оның",
                "source_segment_ids": ["seg_002"],
                "evidence_ids": ["evidence_pronoun"],
                "status": "resolved",
                "method": "model_proposal",
                "grammatical_number": "singular",
                "antecedent_mention_ids": ["mention_erlan"],
                "candidate_mention_ids": ["mention_erlan"],
                "evidence_class": "D_context_resolved",
                "confidence": 0.8,
                "reason": "The possessive refers to the preceding named person.",
            }
        ],
        "people_mentions": [
            {
                "mention_id": "mention_erlan",
                "name": "Ерлан",
                "source_segment_ids": ["seg_001", "seg_002"],
                "confidence": 1.0,
            },
            {
                "mention_id": "mention_nurlan",
                "name": "Нұрлан",
                "source_segment_ids": ["seg_002"],
                "confidence": 1.0,
            },
        ],
        "relationship_claims": [
            {
                "relationship_id": "relationship_parent",
                "relationship_type": "parent_child",
                "subject_mention_id": "mention_erlan",
                "subject_role": "parent",
                "object_mention_id": "mention_nurlan",
                "object_role": "child",
                "source_segment_ids": ["seg_002"],
                "coreference_link_ids": ["coreference_001"],
                "confidence": 0.8,
            }
        ],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert any(issue["code"] == "coreference_reference_invalid" for issue in issues)
    assert len(result.relationship_claims) == 1
    relationship = result.relationship_claims[0]
    assert relationship.evidence_class is EvidenceClass.D_CONTEXT_RESOLVED
    assert "coreference_001" not in relationship.coreference_link_ids
    assert len(relationship.coreference_link_ids) == 1
    attached_link = next(
        link
        for link in result.coreference_links
        if link.coreference_id == relationship.coreference_link_ids[0]
    )
    assert attached_link.method is CoreferenceMethod.DETERMINISTIC_DISCOURSE
    assert attached_link.status is CoreferenceStatus.RESOLVED
    assert attached_link.antecedent_mention_ids == ["mention_erlan"]
    assert not is_auto_acceptable_evidence_class(relationship.evidence_class)
    validate_extraction_result(transcript, result)


def test_conflict_set_preserves_claims_and_cross_links_them() -> None:
    transcript = _transcript(("seg_001", "Ерлан Динара."))
    raw = _explicit_relationship_raw()
    raw["relationship_claims"] = [
        {
            "relationship_id": "relationship_spouse",
            "relationship_type": "spouse",
            "subject_mention_id": "mention_erlan",
            "subject_role": "spouse",
            "object_mention_id": "mention_dinara",
            "object_role": "spouse",
            "source_segment_ids": ["seg_001"],
            "confidence": 0.8,
        },
        {
            "relationship_id": "relationship_parent",
            "relationship_type": "parent_child",
            "subject_mention_id": "mention_erlan",
            "subject_role": "parent",
            "object_mention_id": "mention_dinara",
            "object_role": "child",
            "source_segment_ids": ["seg_001"],
            "confidence": 0.8,
        },
    ]
    raw["conflict_sets"] = [
        {
            "conflict_id": "conflict_001",
            "conflict_type": "relationship",
            "claim_refs": [
                {"object_type": "relationship", "object_id": "relationship_spouse"},
                {"object_type": "relationship", "object_id": "relationship_parent"},
            ],
            "status": "open",
            "detected_by": "model",
            "rationale": "The two relationship types cannot both describe this pair.",
        }
    ]

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert issues == []
    assert len(result.relationship_claims) == 2
    assert len(result.conflict_sets) == 1
    assert result.conflict_sets[0].preferred_claim is None
    assert all(item.conflict_ids == ["conflict_001"] for item in result.relationship_claims)
    validate_extraction_result(transcript, result)


def test_evidence_class_auto_accept_policy_is_fail_closed() -> None:
    assert is_auto_acceptable_evidence_class(EvidenceClass.A_EXPLICIT)
    assert is_auto_acceptable_evidence_class(EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT)
    assert is_auto_acceptable_evidence_class(EvidenceClass.C_SPEAKER_ANCHORED)
    assert not is_auto_acceptable_evidence_class(EvidenceClass.D_CONTEXT_RESOLVED)
    assert not is_auto_acceptable_evidence_class(EvidenceClass.E_INFERRED)
    assert not is_auto_acceptable_evidence_class(EvidenceClass.U_UNCERTAIN)


def test_name_variant_normalization_is_deterministic() -> None:
    with pytest.raises(ValidationError, match="normalized name"):
        NameVariant(
            variant_id="variant_001",
            surface="  Ереке! ",
            normalized="wrong",
            variant_type=NameVariantType.NICKNAME,
            source_segment_ids=["seg_001"],
        )


def test_coreference_contract_rejects_invalid_resolution_states() -> None:
    with pytest.raises(ValidationError, match="exactly one antecedent"):
        CoreferenceLink(
            coreference_id="coreference_001",
            anaphor_text="оның",
            source_segment_ids=["seg_001"],
            evidence_ids=["evidence_001"],
            status=CoreferenceStatus.RESOLVED,
            method=CoreferenceMethod.MODEL_PROPOSAL,
            grammatical_number=GrammaticalNumber.SINGULAR,
            antecedent_mention_ids=["mention_001", "mention_002"],
            candidate_mention_ids=["mention_001", "mention_002"],
            evidence_class=EvidenceClass.D_CONTEXT_RESOLVED,
            confidence=0.5,
            reason="invalid singular resolution",
        )

    with pytest.raises(ValidationError, match="at least two candidates"):
        CoreferenceLink(
            coreference_id="coreference_002",
            anaphor_text="his",
            source_segment_ids=["seg_001"],
            evidence_ids=["evidence_001"],
            status=CoreferenceStatus.AMBIGUOUS,
            method=CoreferenceMethod.MODEL_PROPOSAL,
            grammatical_number=GrammaticalNumber.SINGULAR,
            candidate_mention_ids=["mention_001"],
            evidence_class=EvidenceClass.U_UNCERTAIN,
            confidence=0.5,
            reason="insufficient candidates",
        )
