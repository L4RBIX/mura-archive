"""The product's view of the archive, seeded through canonical persistence.

Every fixture here is written with `ArchiveRepository.persist_pipeline_result`,
the same path the worker uses, rather than by inserting rows. That matters:
these tests are meant to prove the read models reflect what extraction actually
stores, and hand-built rows would let them agree with an archive that never
exists in production.

The rule under test throughout is that nothing is invented. A story knows who
it is about because entity resolution said so, not because a name matched; a
relationship appears because the graph was materialized, not because a claim
was emitted; an unknown date stays unknown.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mura.domain.models import (
    CleanerResult,
    EventDate,
    EvidenceClass,
    EvidenceSpan,
    ExtractionResult,
    FamilyEvent,
    MentionResolution,
    PersonCategory,
    PersonMention,
    PipelineResult,
    RawSegment,
    ReadableSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    ResolutionStatus,
    Story,
    TemporalPrecision,
    TranscriptEnvelope,
    UnresolvedQuestion,
)
from mura.storage.archive import ArchiveRepository
from mura.storage.archive_read import (
    MAX_PAGE_SIZE,
    ArchiveReadRepository,
    ArchiveResourceNotFound,
    clamp_limit,
)
from mura.storage.database import Database, RecordingRepository, RecordingRow

FAMILY = "family_read_a"
OTHER_FAMILY = "family_read_b"
RECORDING = "rec_" + "1" * 32
JOB = "job_" + "1" * 32
TEXT = "Бабушка рассказала, как Марат чинил синий велосипед летом."


def _seed(
    database: Database,
    *,
    family_id: str,
    recording_id: str,
    job_id: str,
    storage_key: str | None = "family/x/original.wav",
) -> None:
    RecordingRepository(database).create_recording_and_job(
        recording_id=recording_id,
        job_id=job_id,
        family_id=family_id,
        speaker_id=f"narrator_{recording_id}",
        speaker_name="Айсұлу",
        original_filename="memory.wav",
        content_type="audio/wav",
        audio_path=f"family/{family_id}/{recording_id}/original.wav",
        storage_key=storage_key,
        storage_backend="local" if storage_key else None,
        audio_language="auto",
        output_language="same_as_transcript",
    )
    with database.session_factory.begin() as session:
        recording = session.get(RecordingRow, recording_id)
        assert recording is not None
        ArchiveRepository.persist_pipeline_result(
            session,
            recording=recording,
            result=_result(recording_id),
        )


def _result(recording_id: str) -> PipelineResult:
    transcript = TranscriptEnvelope(
        recording_id=recording_id,
        duration_seconds=12,
        language_hints=["ru"],
        full_text=TEXT,
        segments=[RawSegment(segment_id="seg_001", start=0, end=12, text=TEXT)],
        asr_model="fixture-asr",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )
    evidence = EvidenceSpan(
        evidence_id="evidence_main",
        segment_id="seg_001",
        text=TEXT,
        evidence_class=EvidenceClass.A_EXPLICIT,
        mention_ids=["mention_babushka", "mention_marat"],
    )
    common = {
        "source_segment_ids": ["seg_001"],
        "evidence_ids": [evidence.evidence_id],
        "evidence_class": EvidenceClass.A_EXPLICIT,
    }
    people = [
        PersonMention(
            mention_id="mention_babushka",
            name="Айсұлу",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="бабушка",
            confidence=1,
            **common,
        ),
        PersonMention(
            mention_id="mention_marat",
            name="Марат",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="муж",
            confidence=1,
            **common,
        ),
    ]
    relationship = RelationshipClaim(
        relationship_id="relationship_001",
        relationship_type=RelationshipType.SPOUSE,
        subject_mention_id="mention_babushka",
        subject_role=RelationshipRole.SPOUSE,
        object_mention_id="mention_marat",
        object_role=RelationshipRole.SPOUSE,
        confidence=1,
        **common,
    )
    event = FamilyEvent(
        event_id="event_001",
        event_type="repair",
        title="Синий велосипед",
        participant_mention_ids=["mention_marat"],
        # Year only. The read model must not turn this into a calendar day.
        date=EventDate(
            value="1963",
            precision=TemporalPrecision.YEAR,
            original_expression="летом 1963",
            approximate=True,
        ),
        location="Алматы",
        description="Марат чинил велосипед во дворе.",
        confidence=1,
        **common,
    )
    story = Story(
        story_id="story_001",
        title="Синий велосипед Марата",
        summary="Бабушка вспоминает, как Марат чинил велосипед летом.",
        person_mention_ids=["mention_babushka", "mention_marat"],
        event_ids=["event_001"],
        **common,
    )
    question = UnresolvedQuestion(
        question_id="question_001",
        question="Кто такой Марат для рассказчицы?",
        reason="Отношение упомянуто неоднозначно.",
        related_mention_ids=["mention_marat"],
        **common,
    )
    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[ReadableSegment(segment_id="seg_001", text=TEXT)],
            full_readable_text=TEXT,
        ),
        extraction=ExtractionResult(
            recording_id=recording_id,
            speaker_id=f"narrator_{recording_id}",
            speaker_name="Айсұлу",
            languages=["ru"],
            evidence_spans=[evidence],
            people_mentions=people,
            relationship_claims=[relationship],
            events=[event],
            stories=[story],
            unresolved_questions=[question],
        ),
        resolutions=[
            MentionResolution(
                mention_id=mention.mention_id,
                status=ResolutionStatus.NEW_PERSON,
                reason="fixture",
            )
            for mention in people
        ],
    )


@pytest.fixture
def archive(tmp_path: Path) -> ArchiveReadRepository:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    _seed(database, family_id=FAMILY, recording_id=RECORDING, job_id=JOB)
    return ArchiveReadRepository(database)


@pytest.fixture
def empty_archive() -> ArchiveReadRepository:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    return ArchiveReadRepository(database)


# --------------------------------------------------------------------- people


def test_people_come_from_the_archive(archive: ArchiveReadRepository) -> None:
    people = archive.list_people(family_id=FAMILY)

    assert {person.display_name for person in people} == {"Айсұлу", "Марат"}
    assert all(person.person_id.startswith("person_") for person in people)


def test_relation_to_speaker_is_reported_as_said(archive: ArchiveReadRepository) -> None:
    marat = next(p for p in archive.list_people(family_id=FAMILY) if p.display_name == "Марат")

    # "муж" was said about the speaker; it is not inferred from the graph.
    assert marat.relation_to_speaker == "муж"


def test_story_counts_are_per_canonical_person(archive: ArchiveReadRepository) -> None:
    for person in archive.list_people(family_id=FAMILY):
        assert person.story_count == 1


# -------------------------------------------------------------- relationships


def test_relationships_come_from_the_materialized_graph(
    archive: ArchiveReadRepository,
) -> None:
    edges = archive.list_relationships(family_id=FAMILY)

    assert len(edges) == 1
    edge = edges[0]
    assert edge.relationship_type == RelationshipType.SPOUSE.value
    # Both endpoints are canonical people, so the client never has to guess.
    known = {person.person_id for person in archive.list_people(family_id=FAMILY)}
    assert edge.subject_person_id in known
    assert edge.object_person_id in known
    # An edge always says which claims produced it.
    assert edge.source_claim_ids


# -------------------------------------------------------------------- stories


def test_story_people_are_resolved_through_mentions_not_names(
    archive: ArchiveReadRepository,
) -> None:
    """The rule this whole milestone exists for.

    The story payload holds mention ids. Turning those into people goes through
    the person-mention claims entity resolution wrote, so the answer is
    canonical ids -- never a name comparison, which would merge two relatives
    who happen to share a name.
    """

    page = archive.list_stories(family_id=FAMILY)
    story = page.items[0]
    known = {person.person_id for person in archive.list_people(family_id=FAMILY)}

    assert story.person_ids
    assert set(story.person_ids) <= known
    assert all(pid.startswith("person_") for pid in story.person_ids)


def test_story_detail_carries_its_source(archive: ArchiveReadRepository) -> None:
    detail = archive.get_story(family_id=FAMILY, story_id="story_001")

    assert detail.title == "Синий велосипед Марата"
    assert detail.speaker_name == "Айсұлу"
    assert detail.source.recording_id == RECORDING
    assert detail.source.claim_ids
    assert {p.display_name for p in detail.people} == {"Айсұлу", "Марат"}


def test_story_detail_preserves_date_precision(archive: ArchiveReadRepository) -> None:
    """A year is a year. Rendering a day nobody said would invent a fact."""

    detail = archive.get_story(family_id=FAMILY, story_id="story_001")
    event = detail.events[0]

    assert event.date is not None
    assert event.date.precision == TemporalPrecision.YEAR.value
    assert event.date.value == "1963"
    assert event.date.approximate is True
    assert event.date.original_expression == "летом 1963"


def test_audio_availability_follows_the_storage_key(tmp_path: Path) -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    # A legacy row with only a filesystem path is not offered for playback.
    _seed(database, family_id=FAMILY, recording_id=RECORDING, job_id=JOB, storage_key=None)

    detail = ArchiveReadRepository(database).get_story(family_id=FAMILY, story_id="story_001")

    assert detail.audio_available is False


def test_story_from_another_family_is_not_found(archive: ArchiveReadRepository) -> None:
    with pytest.raises(ArchiveResourceNotFound):
        archive.get_story(family_id=OTHER_FAMILY, story_id="story_001")


# ------------------------------------------------------------------ bounding


def test_list_limit_is_clamped() -> None:
    # A family archive grows for years; no caller may ask for all of it.
    assert clamp_limit(None) > 0
    assert clamp_limit(10_000) == MAX_PAGE_SIZE
    assert clamp_limit(0) == 1


def test_story_page_reports_the_real_total(archive: ArchiveReadRepository) -> None:
    page = archive.list_stories(family_id=FAMILY, limit=1)

    assert page.page.total == 1
    assert page.page.limit == 1


# -------------------------------------------------------------------- review


def test_review_items_come_from_persisted_questions(
    archive: ArchiveReadRepository,
) -> None:
    items = archive.list_review_items(family_id=FAMILY)

    questions = [item for item in items if item.kind == "open_question"]
    assert len(questions) == 1
    assert questions[0].question == "Кто такой Марат для рассказчицы?"
    assert questions[0].detail == "Отношение упомянуто неоднозначно."
    assert questions[0].recording_id == RECORDING


# ------------------------------------------------------------------ overview


def test_overview_counts_real_rows(archive: ArchiveReadRepository) -> None:
    overview = archive.overview(family_id=FAMILY)

    assert overview.people_count == 2
    assert overview.relationship_count == 1
    assert overview.story_count == 1
    assert overview.recording_count == 1
    assert overview.review_count == 1
    assert len(overview.recent_stories) == 1


# --------------------------------------------------------------------- empty


def test_an_empty_archive_is_empty(empty_archive: ArchiveReadRepository) -> None:
    """No demonstration family is ever substituted for missing data."""

    overview = empty_archive.overview(family_id=FAMILY)

    assert overview.people_count == 0
    assert overview.story_count == 0
    assert overview.recent_stories == []
    assert empty_archive.list_people(family_id=FAMILY) == []
    assert empty_archive.list_relationships(family_id=FAMILY) == []
    assert empty_archive.list_review_items(family_id=FAMILY) == []


def test_another_family_sees_nothing(archive: ArchiveReadRepository) -> None:
    assert archive.list_people(family_id=OTHER_FAMILY) == []
    assert archive.list_relationships(family_id=OTHER_FAMILY) == []
    assert archive.list_stories(family_id=OTHER_FAMILY).items == []
    assert archive.overview(family_id=OTHER_FAMILY).people_count == 0
