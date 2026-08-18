from mura.domain.models import ExtractionResult, KnownPerson, PersonMention, ResolutionStatus
from mura.resolution import resolve_mentions


def test_unverified_legacy_alias_needs_review() -> None:
    extraction = ExtractionResult(
        recording_id="rec_2",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        people_mentions=[
            PersonMention(
                mention_id="mention_001",
                name="Ереке",
                relation_to_speaker="son",
                source_segment_ids=["seg_001"],
                confidence=0.95,
            )
        ],
    )
    known = [
        KnownPerson(
            person_id="person_erlan",
            canonical_name="Ерлан",
            aliases=["Ереке"],
            relation_to_speaker="son",
        )
    ]
    result = resolve_mentions(extraction, known)
    assert result[0].status == ResolutionStatus.NEEDS_REVIEW
    assert result[0].person_id is None
    assert result[0].candidate_person_ids == ["person_erlan"]


def test_conflicting_relation_needs_review() -> None:
    extraction = ExtractionResult(
        recording_id="rec_2",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        people_mentions=[
            PersonMention(
                mention_id="mention_001",
                name="Ерлан",
                relation_to_speaker="brother",
                source_segment_ids=["seg_001"],
                confidence=0.8,
            )
        ],
    )
    known = [
        KnownPerson(
            person_id="person_erlan",
            canonical_name="Ерлан",
            relation_to_speaker="son",
        )
    ]
    result = resolve_mentions(extraction, known)
    assert result[0].status == ResolutionStatus.NEEDS_REVIEW
