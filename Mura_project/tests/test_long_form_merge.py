from mura.domain.models import (
    AssertionMode,
    EvidenceClass,
    ExtractionResult,
    PersonMention,
    RawSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipState,
    RelationshipType,
    TranscriptEnvelope,
)
from mura.long_form import LongFormExtractionPlanner, LongFormPolicy
from mura.long_form_merge import WindowExtraction, merge_window_extractions


def _transcript() -> TranscriptEnvelope:
    segments = [
        RawSegment(segment_id=f"seg_{index}", start=index * 2, end=index * 2 + 1, text=text)
        for index, text in enumerate(
            (
                "Серік Сапарұлы менің ағам.",
                "Ол Айжанға үйленген.",
                "Кейін Серік Нұрбекұлы келді.",
            )
        )
    ]
    return TranscriptEnvelope(
        recording_id="rec_merge",
        duration_seconds=6,
        language_hints=["kk"],
        full_text=" ".join(item.text for item in segments),
        segments=segments,
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def _person(mention_id: str, name: str, segment_id: str) -> PersonMention:
    return PersonMention(
        mention_id=mention_id,
        name=name,
        source_segment_ids=[segment_id],
        evidence_ids=[],
        evidence_class=EvidenceClass.A_EXPLICIT,
        assertion_mode=AssertionMode.EXPLICIT,
        confidence=0.9,
    )


def _result(
    people: list[PersonMention],
    relationships: list[RelationshipClaim] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        recording_id="rec_merge",
        speaker_id="speaker",
        speaker_name="Narrator",
        languages=["kk"],
        people_mentions=people,
        relationship_claims=relationships or [],
    )


def test_overlap_person_and_relationship_are_deduplicated_and_references_remapped() -> None:
    transcript = _transcript()
    planner = LongFormExtractionPlanner(
        LongFormPolicy(
            segment_count_threshold=2,
            target_segments_per_window=2,
            minimum_window_tokens=1,
            pause_boundary_seconds=100,
        )
    )
    plan = planner.plan(transcript)
    first_serik = _person("person_local_1", "Серік Сапарұлы", "seg_1")
    second_serik = _person("another_local_id", "Серік Сапарұлы", "seg_1")
    spouse = _person("spouse_local", "Айжан", "seg_1")
    relationship = RelationshipClaim(
        relationship_id="rel_local",
        relationship_type=RelationshipType.SPOUSE,
        relationship_state=RelationshipState.CURRENT,
        subject_mention_id="another_local_id",
        subject_role=RelationshipRole.SPOUSE,
        object_mention_id="spouse_local",
        object_role=RelationshipRole.SPOUSE,
        source_segment_ids=["seg_1"],
        evidence_ids=[],
        evidence_class=EvidenceClass.A_EXPLICIT,
        confidence=0.9,
    )

    merged, report = merge_window_extractions(
        recording_id="rec_merge",
        speaker_id="speaker",
        speaker_name="Narrator",
        windows=[
            WindowExtraction(window=plan.windows[0], extraction=_result([first_serik])),
            WindowExtraction(
                window=plan.windows[1],
                extraction=_result([second_serik, spouse], [relationship]),
            ),
        ],
    )

    assert [person.name for person in merged.people_mentions].count("Серік Сапарұлы") == 1
    assert merged.relationship_claims[0].subject_mention_id in {
        person.mention_id for person in merged.people_mentions
    }
    assert report.duplicate_people == 1
    assert report.remapped > 0


def test_same_name_without_shared_evidence_remains_separate_for_review() -> None:
    transcript = _transcript()
    planner = LongFormExtractionPlanner(LongFormPolicy(segment_count_threshold=2))
    plan = planner.plan(transcript)

    merged, report = merge_window_extractions(
        recording_id="rec_merge",
        speaker_id="speaker",
        speaker_name="Narrator",
        windows=[
            WindowExtraction(
                window=plan.windows[0],
                extraction=_result([_person("serik_a", "Серік", "seg_0")]),
            ),
            WindowExtraction(
                window=plan.windows[-1],
                extraction=_result([_person("serik_b", "Серік", "seg_2")]),
            ),
        ],
    )

    assert len(merged.people_mentions) == 2
    assert report.duplicate_people == 0
    assert report.review_required == 1
