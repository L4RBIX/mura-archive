from __future__ import annotations

from pathlib import Path

from mura.domain.models import (
    AssertionMode,
    CleanerResult,
    EventDate,
    EvidenceClass,
    EvidenceSpan,
    ExtractionResult,
    FamilyEvent,
    MentionResolution,
    NameVariant,
    NameVariantType,
    PersonCategory,
    PersonDescription,
    PersonMention,
    PipelineResult,
    RawSegment,
    ReadableSegment,
    ResolutionStatus,
    TranscriptEnvelope,
    VerificationStatus,
)
from mura.storage.archive import ArchiveRepository
from mura.storage.conflict_resolution import ConflictAction, ConflictResolutionService
from mura.storage.database import Database, RecordingRepository, RecordingRow
from mura.storage.generic_claims import persist_generic_claims
from mura.storage.generic_review import GenericProfileRepository, UnifiedConflictReviewService


def _transcript(recording_id: str, text: str) -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id=recording_id,
        duration_seconds=5,
        language_hints=["kk"],
        full_text=text,
        segments=[RawSegment(segment_id="seg_001", start=0, end=5, text=text)],
        asr_model="fixture-asr",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )


def _result(
    *,
    recording_id: str,
    name: str,
    birth_year: str | None = None,
    alias: str | None = None,
    description: str | None = None,
    location: str | None = None,
    person_id: str | None = None,
) -> PipelineResult:
    pieces = [name]
    if birth_year:
        pieces.append(f"{birth_year} жылы туған")
    if alias:
        pieces.append(f"оны {alias} деп атайтын")
    if description:
        pieces.append(description)
    if location:
        pieces.append(location)
    text = ". ".join(pieces) + "."
    transcript = _transcript(recording_id, text)
    evidence = EvidenceSpan(
        evidence_id="evidence_001",
        segment_id="seg_001",
        text=text,
        evidence_class=EvidenceClass.A_EXPLICIT,
        mention_ids=["mention_001"],
    )
    variants = []
    if alias:
        variants.append(
            NameVariant(
                variant_id="variant_alias",
                surface=alias,
                normalized=alias.casefold(),
                variant_type=NameVariantType.EXPLICIT_ALIAS,
                language="kk",
                script="Cyrl",
                source_segment_ids=["seg_001"],
                evidence_ids=["evidence_001"],
                verification_status=VerificationStatus.UNREVIEWED,
            )
        )
    mention = PersonMention(
        mention_id="mention_001",
        name=name,
        name_variants=variants,
        category=PersonCategory.FAMILY_MEMBER,
        relation_to_speaker="son",
        source_segment_ids=["seg_001"],
        evidence_ids=["evidence_001"],
        evidence_class=EvidenceClass.A_EXPLICIT,
        assertion_mode=AssertionMode.EXPLICIT,
        confidence=1,
    )
    events = []
    if birth_year:
        events.append(
            FamilyEvent(
                event_id="event_birth",
                event_type="birth",
                title=f"{name} was born",
                participant_mention_ids=["mention_001"],
                date=EventDate(
                    value=birth_year,
                    precision="year",
                    original_expression=f"{birth_year} жылы",
                ),
                location=location,
                description=f"{name} was born in {birth_year}",
                source_segment_ids=["seg_001"],
                evidence_ids=["evidence_001"],
                evidence_class=EvidenceClass.A_EXPLICIT,
                assertion_mode=AssertionMode.EXPLICIT,
                confidence=1,
            )
        )
    descriptions = []
    if description:
        descriptions.append(
            PersonDescription(
                description_id="description_001",
                person_mention_id="mention_001",
                description=description,
                perspective="speaker",
                source_segment_ids=["seg_001"],
                evidence_ids=["evidence_001"],
                evidence_class=EvidenceClass.A_EXPLICIT,
                assertion_mode=AssertionMode.EXPLICIT,
                confidence=1,
            )
        )
    resolution = (
        MentionResolution(
            mention_id="mention_001",
            status=ResolutionStatus.RESOLVED,
            person_id=person_id,
            candidate_person_ids=[person_id],
            reason="fixture archive identity",
        )
        if person_id
        else MentionResolution(
            mention_id="mention_001",
            status=ResolutionStatus.NEW_PERSON,
            reason="new fixture person",
        )
    )
    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[ReadableSegment(segment_id="seg_001", text=text)],
            full_readable_text=text,
        ),
        extraction=ExtractionResult(
            schema_version="extraction-v2",
            recording_id=recording_id,
            speaker_id="speaker_1",
            speaker_name="Күләш",
            evidence_spans=[evidence],
            people_mentions=[mention],
            events=events,
            descriptions=descriptions,
        ),
        resolutions=[resolution],
    )


def _create_recording(
    repository: RecordingRepository,
    tmp_path: Path,
    recording_id: str,
) -> None:
    audio = tmp_path / f"{recording_id}.wav"
    audio.write_bytes(b"audio")
    repository.create_recording_and_job(
        recording_id=recording_id,
        job_id=f"job_{recording_id}",
        family_id="family_1",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        original_filename=audio.name,
        content_type="audio/wav",
        audio_path=audio,
    )


def _persist(
    database: Database,
    *,
    recording_id: str,
    result: PipelineResult,
):
    with database.session_factory.begin() as session:
        recording = session.get(RecordingRow, recording_id)
        assert recording is not None
        ConflictResolutionService.persist_pipeline_result(
            session,
            recording=recording,
            result=result,
        )
        return persist_generic_claims(
            session,
            recording=recording,
            result=result,
        )


def test_generic_facets_materialize_idempotent_profile(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'profile.db'}")
    database.create_schema()
    recordings = RecordingRepository(database)
    profiles = GenericProfileRepository(database)
    _create_recording(recordings, tmp_path, "rec_1")

    result = _result(
        recording_id="rec_1",
        name="Ерлан",
        birth_year="1978",
        alias="Ереке",
        description="Ол сабырлы инженер еді",
        location="Қарағанды",
    )
    report = _persist(database, recording_id="rec_1", result=result)

    assert report.projected_claims == 5
    assert report.open_conflicts == 0
    assert report.materialized_profiles == 1
    profile = profiles.list_profiles(family_id="family_1")[0]
    assert profile.birth_date is not None
    assert profile.birth_date.value == "1978"
    assert [item.value for item in profile.aliases] == ["Ереке"]
    assert [item.value for item in profile.locations] == ["Қарағанды"]
    assert [item.value for item in profile.descriptions] == ["Ол сабырлы инженер еді"]
    assert len(profile.events) == 1

    repeated = _persist(database, recording_id="rec_1", result=result)
    assert repeated.projected_claims == 0
    assert len(profiles.list_profiles(family_id="family_1")) == 1


def test_temporal_conflict_requires_preferred_claim_and_reopens(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'dates.db'}")
    database.create_schema()
    recordings = RecordingRepository(database)
    archive = ArchiveRepository(database)
    profiles = GenericProfileRepository(database)
    review = UnifiedConflictReviewService(database)

    _create_recording(recordings, tmp_path, "rec_1")
    first = _result(recording_id="rec_1", name="Ерлан", birth_year="1978")
    _persist(database, recording_id="rec_1", result=first)
    person_id = archive.list_people("family_1")[0].person_id

    _create_recording(recordings, tmp_path, "rec_2")
    second = _result(
        recording_id="rec_2",
        name="Ерлан",
        birth_year="1979",
        person_id=person_id,
    )
    report = _persist(database, recording_id="rec_2", result=second)
    assert report.open_conflicts == 1
    profile = profiles.get_profile(family_id="family_1", person_id=person_id)
    assert profile.birth_date is None

    conflict = next(
        item
        for item in review.list_conflicts(family_id="family_1", status="open")
        if item.conflict_type == "temporal"
    )
    preferred = next(
        claim for claim in conflict.claims if claim.payload["normalized_value"] == "1978"
    )
    resolved = review.resolve(
        family_id="family_1",
        conflict_id=conflict.conflict_id,
        preferred_claim_id=preferred.claim_id,
        reviewer_reference="reviewer:family",
        note="The family confirmed 1978.",
    )
    assert resolved.conflict.status == "resolved"
    profile = profiles.get_profile(family_id="family_1", person_id=person_id)
    assert profile.birth_date is not None
    assert profile.birth_date.value == "1978"

    _create_recording(recordings, tmp_path, "rec_3")
    third = _result(
        recording_id="rec_3",
        name="Ерлан",
        birth_year="1980",
        person_id=person_id,
    )
    reopened_report = _persist(database, recording_id="rec_3", result=third)
    assert reopened_report.open_conflicts == 1
    reopened = review.get_conflict(
        family_id="family_1",
        conflict_id=conflict.conflict_id,
    )
    assert reopened.status == "open"
    assert reopened.preferred_claim_id is None
    assert [decision.action for decision in reopened.decisions] == [
        ConflictAction.RESOLVE,
        ConflictAction.AUTO_REOPEN,
    ]
    assert profiles.get_profile(family_id="family_1", person_id=person_id).birth_date is None


def test_alias_collision_is_identity_conflict(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'aliases.db'}")
    database.create_schema()
    recordings = RecordingRepository(database)
    profiles = GenericProfileRepository(database)
    review = UnifiedConflictReviewService(database)

    _create_recording(recordings, tmp_path, "rec_1")
    _persist(
        database,
        recording_id="rec_1",
        result=_result(recording_id="rec_1", name="Ерлан", alias="Ереке"),
    )
    _create_recording(recordings, tmp_path, "rec_2")
    report = _persist(
        database,
        recording_id="rec_2",
        result=_result(recording_id="rec_2", name="Ермек", alias="Ереке"),
    )

    assert report.open_conflicts == 1
    identity = next(
        item
        for item in review.list_conflicts(family_id="family_1", status="open")
        if item.conflict_type == "identity"
    )
    assert len(identity.claim_ids) == 2
    assert all(not profile.aliases for profile in profiles.list_profiles(family_id="family_1"))

    preferred = next(
        claim
        for claim in identity.claims
        if claim.payload["source_object_id"].startswith("mention_001")
        and claim.recording_id == "rec_1"
    )
    review.resolve(
        family_id="family_1",
        conflict_id=identity.conflict_id,
        preferred_claim_id=preferred.claim_id,
        reviewer_reference="reviewer:family",
        note="The alias belongs to Erlan.",
    )
    profile_alias_counts = sorted(
        len(profile.aliases) for profile in profiles.list_profiles(family_id="family_1")
    )
    assert profile_alias_counts == [0, 1]
