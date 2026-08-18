from __future__ import annotations

from pathlib import Path

from mura.domain.models import (
    CleanerResult,
    CorrectionKind,
    DetectedCorrection,
    EvidenceClass,
    EvidenceSpan,
    ExtractionResult,
    MentionResolution,
    PersonCategory,
    PersonMention,
    PipelineResult,
    RawSegment,
    ReadableSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipState,
    RelationshipType,
    ResolutionStatus,
    TranscriptEnvelope,
)
from mura.storage.archive import ArchiveRepository
from mura.storage.database import Database, RecordingRepository, RecordingRow


def _transcript(recording_id: str, text: str) -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id=recording_id,
        duration_seconds=8,
        language_hints=["kk"],
        full_text=text,
        segments=[RawSegment(segment_id="seg_001", start=0, end=8, text=text)],
        asr_model="fixture-asr",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )


def _result(
    *,
    recording_id: str,
    relationship_type: RelationshipType,
    subject_role: RelationshipRole,
    object_role: RelationshipRole,
    person_ids: dict[str, str] | None = None,
    evidence_class: EvidenceClass = EvidenceClass.A_EXPLICIT,
    include_correction: bool = False,
    relationship_state: RelationshipState = RelationshipState.CURRENT,
) -> PipelineResult:
    text = "Ерлан мен Нұрлан туралы отбасылық әңгіме."
    transcript = _transcript(recording_id, text)
    evidence = EvidenceSpan(
        evidence_id="evidence_relationship",
        segment_id="seg_001",
        text=text,
        evidence_class=evidence_class,
        mention_ids=["mention_erlan", "mention_nurlan"],
    )
    people = [
        PersonMention(
            mention_id="mention_erlan",
            name="Ерлан",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="son",
            source_segment_ids=["seg_001"],
            evidence_ids=[evidence.evidence_id],
            evidence_class=evidence_class,
            confidence=1,
        ),
        PersonMention(
            mention_id="mention_nurlan",
            name="Нұрлан",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="grandson",
            source_segment_ids=["seg_001"],
            evidence_ids=[evidence.evidence_id],
            evidence_class=evidence_class,
            confidence=1,
        ),
    ]
    relationship = RelationshipClaim(
        relationship_id="relationship_001",
        relationship_type=relationship_type,
        relationship_state=relationship_state,
        subject_mention_id="mention_erlan",
        subject_role=subject_role,
        object_mention_id="mention_nurlan",
        object_role=object_role,
        source_segment_ids=["seg_001"],
        evidence_ids=[evidence.evidence_id],
        evidence_class=evidence_class,
        confidence=1,
    )
    resolutions = []
    for mention in people:
        person_id = (person_ids or {}).get(mention.name)
        if person_id is None:
            resolutions.append(
                MentionResolution(
                    mention_id=mention.mention_id,
                    status=ResolutionStatus.NEW_PERSON,
                    reason="new fixture person",
                )
            )
        else:
            resolutions.append(
                MentionResolution(
                    mention_id=mention.mention_id,
                    status=ResolutionStatus.RESOLVED,
                    person_id=person_id,
                    candidate_person_ids=[person_id],
                    reason="fixture archive identity",
                )
            )

    corrections = []
    if include_correction:
        corrections.append(
            DetectedCorrection(
                kind=CorrectionKind.SPEAKER_SELF_CORRECTION,
                subject="Ерланның туған жылы",
                original_value="1960",
                corrected_value="1961",
                source_segment_ids=["seg_001"],
                explanation="speaker corrected the year in the same recording",
                confidence=1,
            )
        )

    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[ReadableSegment(segment_id="seg_001", text=text)],
            detected_corrections=corrections,
            full_readable_text=text,
        ),
        extraction=ExtractionResult(
            schema_version="extraction-v2",
            recording_id=recording_id,
            speaker_id="speaker_1",
            speaker_name="Күләш",
            evidence_spans=[evidence],
            people_mentions=people,
            relationship_claims=[relationship],
        ),
        resolutions=resolutions,
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
        return ArchiveRepository.persist_pipeline_result(
            session,
            recording=recording,
            result=result,
        )


def test_archive_persists_claims_corrections_and_materialized_graph(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'archive.db'}")
    database.create_schema()
    recording_repository = RecordingRepository(database)
    archive = ArchiveRepository(database)
    _create_recording(recording_repository, tmp_path, "rec_1")

    result = _result(
        recording_id="rec_1",
        relationship_type=RelationshipType.PARENT_CHILD,
        subject_role=RelationshipRole.PARENT,
        object_role=RelationshipRole.CHILD,
        include_correction=True,
    )
    report = _persist(database, recording_id="rec_1", result=result)

    assert report.people_upserted == 2
    assert report.claims_persisted == 3
    assert report.corrections_persisted == 1
    assert report.open_conflicts == 0
    assert report.graph_edges == 1
    assert len(archive.list_people("family_1")) == 2
    assert len(archive.list_claims("family_1")) == 3
    assert len(archive.list_corrections("family_1")) == 1

    edge = archive.list_graph_edges("family_1")[0]
    assert edge.relationship_type == RelationshipType.PARENT_CHILD.value
    assert edge.subject_role == RelationshipRole.PARENT.value
    assert edge.object_role == RelationshipRole.CHILD.value

    context = archive.build_resolution_context(
        family_id="family_1",
        speaker_id="speaker_1",
    )
    profiles = {profile.person.canonical_name: profile for profile in context.profiles}
    assert profiles["Ерлан"].child_person_ids == [profiles["Нұрлан"].person.person_id]
    assert profiles["Нұрлан"].parent_person_ids == [profiles["Ерлан"].person.person_id]
    assert profiles["Ерлан"].generation_relative_to_speaker == 1
    assert profiles["Нұрлан"].generation_relative_to_speaker == 2

    repeated = _persist(database, recording_id="rec_1", result=result)
    assert repeated.claims_persisted == 0
    assert repeated.corrections_persisted == 0
    assert repeated.graph_edges == 1
    assert len(archive.list_claims("family_1")) == 3


def test_competing_grounded_relationships_preserve_claims_and_remove_edge(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'conflicts.db'}")
    database.create_schema()
    recording_repository = RecordingRepository(database)
    archive = ArchiveRepository(database)
    _create_recording(recording_repository, tmp_path, "rec_1")

    first = _result(
        recording_id="rec_1",
        relationship_type=RelationshipType.PARENT_CHILD,
        subject_role=RelationshipRole.PARENT,
        object_role=RelationshipRole.CHILD,
    )
    _persist(database, recording_id="rec_1", result=first)
    people = {row.canonical_name: row.person_id for row in archive.list_people("family_1")}

    _create_recording(recording_repository, tmp_path, "rec_2")
    competing = _result(
        recording_id="rec_2",
        relationship_type=RelationshipType.SPOUSE,
        subject_role=RelationshipRole.SPOUSE,
        object_role=RelationshipRole.SPOUSE,
        person_ids=people,
    )
    report = _persist(database, recording_id="rec_2", result=competing)

    relationship_claims = [
        claim for claim in archive.list_claims("family_1") if claim.object_type == "relationship"
    ]
    assert len(relationship_claims) == 2
    assert {claim.status for claim in relationship_claims} == {"disputed"}
    assert report.open_conflicts == 1
    assert len(archive.list_conflicts("family_1")) == 1
    assert report.graph_edges == 0
    assert archive.list_graph_edges("family_1") == []


def test_uncertain_competing_relationship_does_not_block_grounded_graph(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'uncertain.db'}")
    database.create_schema()
    recording_repository = RecordingRepository(database)
    archive = ArchiveRepository(database)
    _create_recording(recording_repository, tmp_path, "rec_1")
    first = _result(
        recording_id="rec_1",
        relationship_type=RelationshipType.PARENT_CHILD,
        subject_role=RelationshipRole.PARENT,
        object_role=RelationshipRole.CHILD,
    )
    _persist(database, recording_id="rec_1", result=first)
    people = {row.canonical_name: row.person_id for row in archive.list_people("family_1")}

    _create_recording(recording_repository, tmp_path, "rec_2")
    uncertain = _result(
        recording_id="rec_2",
        relationship_type=RelationshipType.SPOUSE,
        subject_role=RelationshipRole.SPOUSE,
        object_role=RelationshipRole.SPOUSE,
        person_ids=people,
        evidence_class=EvidenceClass.U_UNCERTAIN,
    )
    report = _persist(database, recording_id="rec_2", result=uncertain)

    assert report.open_conflicts == 0
    assert report.graph_edges == 1
    assert len(archive.list_graph_edges("family_1")) == 1


def test_former_relationship_is_preserved_but_not_materialized_as_active_graph(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'former.db'}")
    database.create_schema()
    recording_repository = RecordingRepository(database)
    archive = ArchiveRepository(database)
    _create_recording(recording_repository, tmp_path, "rec_former")

    result = _result(
        recording_id="rec_former",
        relationship_type=RelationshipType.SPOUSE,
        subject_role=RelationshipRole.SPOUSE,
        object_role=RelationshipRole.SPOUSE,
        relationship_state=RelationshipState.FORMER,
        evidence_class=EvidenceClass.U_UNCERTAIN,
    )
    report = _persist(database, recording_id="rec_former", result=result)

    relationship_claims = [
        claim for claim in archive.list_claims("family_1") if claim.object_type == "relationship"
    ]
    assert len(relationship_claims) == 1
    assert relationship_claims[0].status == "historical"
    assert report.graph_edges == 0
    assert archive.list_graph_edges("family_1") == []
