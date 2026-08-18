from __future__ import annotations

import pytest
from pydantic import ValidationError

from mura.domain.models import (
    CleanerResult,
    CorrectionKind,
    DetectedCorrection,
    EvidenceSpan,
    ExtractionResult,
    PersonDescription,
    PersonMention,
    RawSegment,
    ReadableSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    TranscriptEnvelope,
    UncertainFragment,
)
from mura.validation import (
    ContractValidationError,
    validate_cleaner_result,
    validate_extraction_result,
)


def transcript(*segments: tuple[str, str]) -> TranscriptEnvelope:
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
        recording_id="rec_1",
        duration_seconds=float(len(raw_segments) * 10),
        full_text=" ".join(segment.text for segment in raw_segments),
        segments=raw_segments,
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="v1",
    )


def test_cleaner_requires_exact_segment_coverage() -> None:
    raw = transcript(("seg_001", "әкемнің аты сапар"))
    result = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_999", text="Wrong")],
        full_readable_text="Wrong",
    )
    with pytest.raises(ContractValidationError, match="coverage mismatch"):
        validate_cleaner_result(raw, result)


def test_cleaner_rejects_uncertain_fragment_from_wrong_segment() -> None:
    raw = transcript(("seg_001", "она была ичи"), ("seg_002", "другая фраза"))
    result = CleanerResult(
        readable_segments=[
            ReadableSegment(segment_id="seg_001", text="Она была ичи."),
            ReadableSegment(segment_id="seg_002", text="Другая фраза."),
        ],
        uncertain_fragments=[
            UncertainFragment(
                source_segment_ids=["seg_002"],
                raw_text="ичи",
                reason="unclear ASR token",
            )
        ],
        full_readable_text="Она была ичи. Другая фраза.",
    )

    with pytest.raises(ContractValidationError, match="not present"):
        validate_cleaner_result(raw, result)


def test_cleaner_preserves_uncertain_text_verbatim() -> None:
    raw = transcript(("seg_001", "она была ичи и любила читать"))
    result = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_001", text="Она была и любила читать.")],
        uncertain_fragments=[
            UncertainFragment(
                source_segment_ids=["seg_001"],
                raw_text="ичи",
                reason="unclear ASR token",
            )
        ],
        full_readable_text="Она была и любила читать.",
    )

    with pytest.raises(ContractValidationError, match="readable preservation"):
        validate_cleaner_result(raw, result)


def test_cleaner_does_not_allow_guess_for_uncertain_fragment() -> None:
    with pytest.raises(ValidationError):
        UncertainFragment.model_validate(
            {
                "source_segment_ids": ["seg_001"],
                "raw_text": "ичи",
                "possible_interpretation": "и чистая",
                "reason": "guess",
            }
        )


def test_cleaner_rejects_same_span_as_correction_and_uncertainty() -> None:
    malformed_whatsapp = "w\u0432ats\u0430\u043f"
    raw = transcript(("seg_001", f"она отправила через {malformed_whatsapp}"))
    result = CleanerResult(
        readable_segments=[
            ReadableSegment(segment_id="seg_001", text="Она отправила через WhatsApp.")
        ],
        detected_corrections=[
            DetectedCorrection(
                kind=CorrectionKind.ASR_NORMALIZATION,
                original_value=malformed_whatsapp,
                corrected_value="WhatsApp",
                source_segment_ids=["seg_001"],
                explanation="unambiguous product name",
                confidence=1,
            )
        ],
        uncertain_fragments=[
            UncertainFragment(
                source_segment_ids=["seg_001"],
                raw_text=malformed_whatsapp,
                reason="unclear token",
            )
        ],
        full_readable_text="Она отправила через WhatsApp.",
    )

    with pytest.raises(ContractValidationError, match="cannot also"):
        validate_cleaner_result(raw, result)


def test_relationship_requires_canonical_role_pair() -> None:
    with pytest.raises(ValidationError, match="invalid role pair"):
        RelationshipClaim(
            relationship_id="relationship_001",
            relationship_type=RelationshipType.PARENT_CHILD,
            subject_mention_id="mention_parent",
            subject_role=RelationshipRole.CHILD,
            object_mention_id="mention_child",
            object_role=RelationshipRole.PARENT,
            source_segment_ids=["seg_001"],
            confidence=1,
        )


def test_extraction_rejects_broken_relationship_reference() -> None:
    raw = transcript(("seg_001", "әкемнің аты сапар"))
    result = ExtractionResult(
        recording_id="rec_1",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        people_mentions=[
            PersonMention(
                mention_id="mention_001",
                name="Сапар",
                source_segment_ids=["seg_001"],
                confidence=1,
            )
        ],
        relationship_claims=[
            RelationshipClaim(
                relationship_id="relationship_001",
                relationship_type=RelationshipType.PARENT_CHILD,
                subject_mention_id="mention_001",
                subject_role=RelationshipRole.PARENT,
                object_mention_id="mention_missing",
                object_role=RelationshipRole.CHILD,
                source_segment_ids=["seg_001"],
                confidence=1,
            )
        ],
    )
    with pytest.raises(ContractValidationError, match="unknown object"):
        validate_extraction_result(raw, result)


def test_nurgali_is_younger_sibling_of_sapar() -> None:
    raw = transcript(("seg_001", "Сапардың інісі Нұрғали еді"))
    result = ExtractionResult(
        recording_id="rec_1",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        people_mentions=[
            PersonMention(
                mention_id="mention_sapar",
                name="Сапар",
                source_segment_ids=["seg_001"],
                confidence=1,
            ),
            PersonMention(
                mention_id="mention_nurgali",
                name="Нұрғали",
                source_segment_ids=["seg_001"],
                confidence=1,
            ),
        ],
        relationship_claims=[
            RelationshipClaim(
                relationship_id="relationship_001",
                relationship_type=RelationshipType.SIBLING,
                subject_mention_id="mention_sapar",
                subject_role=RelationshipRole.OLDER_SIBLING,
                object_mention_id="mention_nurgali",
                object_role=RelationshipRole.YOUNGER_SIBLING,
                source_segment_ids=["seg_001"],
                confidence=1,
            )
        ],
    )

    validate_extraction_result(raw, result)
    relationship = result.relationship_claims[0]
    assert relationship.subject_mention_id == "mention_sapar"
    assert relationship.subject_role is RelationshipRole.OLDER_SIBLING
    assert relationship.object_mention_id == "mention_nurgali"
    assert relationship.object_role is RelationshipRole.YOUNGER_SIBLING


def _basketball_extraction(
    description_person_id: str,
) -> tuple[TranscriptEnvelope, ExtractionResult]:
    raw = transcript(
        ("seg_019", "Нұрлан келді"),
        ("seg_020", "Диас баскетбол ойнағанды жақсы көреді"),
    )
    result = ExtractionResult(
        recording_id="rec_1",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        evidence_spans=[
            EvidenceSpan(
                evidence_id="evidence_description",
                segment_id="seg_020",
                text="Диас баскетбол ойнағанды жақсы көреді",
                start_char=0,
                end_char=len("Диас баскетбол ойнағанды жақсы көреді"),
                mention_ids=["mention_dias"],
            )
        ],
        people_mentions=[
            PersonMention(
                mention_id="mention_nurlan",
                name="Нұрлан",
                source_segment_ids=["seg_019"],
                confidence=1,
            ),
            PersonMention(
                mention_id="mention_dias",
                name="Диас",
                source_segment_ids=["seg_020"],
                confidence=1,
            ),
        ],
        descriptions=[
            PersonDescription(
                description_id="description_001",
                person_mention_id=description_person_id,
                description="баскетбол ойнағанды жақсы көреді",
                perspective="Күләш",
                source_segment_ids=["seg_020"],
                evidence_ids=["evidence_description"],
                confidence=1,
            )
        ],
    )
    return raw, result


def test_description_rejects_dias_trait_assigned_to_nurlan() -> None:
    raw, result = _basketball_extraction("mention_nurlan")
    with pytest.raises(ContractValidationError, match="no evidence overlap"):
        validate_extraction_result(raw, result)


def test_description_accepts_dias_trait_assigned_to_dias() -> None:
    raw, result = _basketball_extraction("mention_dias")
    validate_extraction_result(raw, result)
