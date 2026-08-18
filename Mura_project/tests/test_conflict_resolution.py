from __future__ import annotations

from pathlib import Path

import pytest

from mura.domain.models import (
    CleanerResult,
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
    RelationshipType,
    ResolutionStatus,
    TranscriptEnvelope,
)
from mura.storage.archive import ArchiveRepository
from mura.storage.conflict_resolution import (
    ConflictAction,
    ConflictNotFoundError,
    ConflictResolutionError,
    ConflictResolutionService,
)
from mura.storage.database import Database, RecordingRepository, RecordingRow


def _transcript(recording_id: str) -> TranscriptEnvelope:
    text = "Ерлан мен Нұрлан туралы отбасылық әңгіме."
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
    relationship_type: RelationshipType,
    subject_role: RelationshipRole,
    object_role: RelationshipRole,
    person_ids: dict[str, str] | None = None,
) -> PipelineResult:
    transcript = _transcript(recording_id)
    evidence = EvidenceSpan(
        evidence_id=f"evidence_{recording_id}",
        segment_id="seg_001",
        text=transcript.full_text,
        evidence_class=EvidenceClass.A_EXPLICIT,
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
            evidence_class=EvidenceClass.A_EXPLICIT,
            confidence=1,
        ),
        PersonMention(
            mention_id="mention_nurlan",
            name="Нұрлан",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="grandson",
            source_segment_ids=["seg_001"],
            evidence_ids=[evidence.evidence_id],
            evidence_class=EvidenceClass.A_EXPLICIT,
            confidence=1,
        ),
    ]
    relationship = RelationshipClaim(
        relationship_id=f"relationship_{recording_id}",
        relationship_type=relationship_type,
        subject_mention_id="mention_erlan",
        subject_role=subject_role,
        object_mention_id="mention_nurlan",
        object_role=object_role,
        source_segment_ids=["seg_001"],
        evidence_ids=[evidence.evidence_id],
        evidence_class=EvidenceClass.A_EXPLICIT,
        confidence=1,
    )
    resolutions: list[MentionResolution] = []
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
    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[ReadableSegment(segment_id="seg_001", text=transcript.full_text)],
            full_readable_text=transcript.full_text,
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
    *,
    family_id: str = "family_1",
) -> None:
    audio = tmp_path / f"{recording_id}.wav"
    audio.write_bytes(b"audio")
    repository.create_recording_and_job(
        recording_id=recording_id,
        job_id=f"job_{recording_id}",
        family_id=family_id,
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
        return ConflictResolutionService.persist_pipeline_result(
            session,
            recording=recording,
            result=result,
        )


def _seed_conflict(tmp_path: Path):
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'review.db'}")
    database.create_schema()
    recordings = RecordingRepository(database)
    archive = ArchiveRepository(database)
    service = ConflictResolutionService(database)

    _create_recording(recordings, tmp_path, "rec_1")
    parent = _result(
        recording_id="rec_1",
        relationship_type=RelationshipType.PARENT_CHILD,
        subject_role=RelationshipRole.PARENT,
        object_role=RelationshipRole.CHILD,
    )
    _persist(database, recording_id="rec_1", result=parent)
    people = {row.canonical_name: row.person_id for row in archive.list_people("family_1")}

    _create_recording(recordings, tmp_path, "rec_2")
    spouse = _result(
        recording_id="rec_2",
        relationship_type=RelationshipType.SPOUSE,
        subject_role=RelationshipRole.SPOUSE,
        object_role=RelationshipRole.SPOUSE,
        person_ids=people,
    )
    report = _persist(database, recording_id="rec_2", result=spouse)
    assert report.open_conflicts == 1
    conflict = service.list_conflicts(family_id="family_1", status="open")[0]
    return database, recordings, archive, service, parent, spouse, people, conflict


def test_resolved_preference_survives_reconciliation(tmp_path: Path) -> None:
    database, _recordings, archive, service, _parent, spouse, _people, conflict = _seed_conflict(
        tmp_path
    )
    preferred = next(claim for claim in conflict.claims if claim.predicate == "parent_child")

    resolved = service.resolve(
        family_id="family_1",
        conflict_id=conflict.conflict_id,
        preferred_claim_id=preferred.claim_id,
        reviewer_reference="reviewer:grandmother",
        note="The narrator confirmed the parent-child relationship.",
    )

    assert resolved.conflict.status == "resolved"
    assert resolved.conflict.preferred_claim_id == preferred.claim_id
    assert resolved.graph_edges == 1
    assert {claim.status for claim in resolved.conflict.claims} == {"accepted", "rejected"}
    edge = archive.list_graph_edges("family_1")[0]
    assert edge.relationship_type == RelationshipType.PARENT_CHILD.value

    replay = _persist(database, recording_id="rec_2", result=spouse)
    assert replay.open_conflicts == 0
    assert replay.graph_edges == 1
    after_replay = service.get_conflict(
        family_id="family_1",
        conflict_id=conflict.conflict_id,
    )
    assert after_replay.status == "resolved"
    assert after_replay.preferred_claim_id == preferred.claim_id
    assert [decision.action for decision in after_replay.decisions] == [ConflictAction.RESOLVE]


def test_new_competing_claim_reopens_resolved_conflict(tmp_path: Path) -> None:
    database, recordings, archive, service, _parent, _spouse, people, conflict = _seed_conflict(
        tmp_path
    )
    preferred = next(claim for claim in conflict.claims if claim.predicate == "parent_child")
    service.resolve(
        family_id="family_1",
        conflict_id=conflict.conflict_id,
        preferred_claim_id=preferred.claim_id,
        reviewer_reference="reviewer:grandmother",
        note="Initial human decision.",
    )

    _create_recording(recordings, tmp_path, "rec_3")
    sibling = _result(
        recording_id="rec_3",
        relationship_type=RelationshipType.SIBLING,
        subject_role=RelationshipRole.SIBLING,
        object_role=RelationshipRole.SIBLING,
        person_ids=people,
    )
    report = _persist(database, recording_id="rec_3", result=sibling)

    assert report.open_conflicts == 1
    assert report.graph_edges == 0
    assert archive.list_graph_edges("family_1") == []
    reopened = service.get_conflict(family_id="family_1", conflict_id=conflict.conflict_id)
    assert reopened.status == "open"
    assert reopened.preferred_claim_id is None
    assert len(reopened.claim_ids) == 3
    assert [decision.action for decision in reopened.decisions] == [
        ConflictAction.RESOLVE,
        ConflictAction.AUTO_REOPEN,
    ]
    assert {claim.status for claim in reopened.claims} == {"disputed"}


def test_dismiss_and_manual_reopen_keep_graph_safe(tmp_path: Path) -> None:
    _database, _recordings, archive, service, _parent, _spouse, _people, conflict = _seed_conflict(
        tmp_path
    )

    dismissed = service.dismiss(
        family_id="family_1",
        conflict_id=conflict.conflict_id,
        reviewer_reference="reviewer:archivist",
        note="Neither statement should be materialized yet.",
    )
    assert dismissed.conflict.status == "dismissed"
    assert dismissed.graph_edges == 0
    assert {claim.status for claim in dismissed.conflict.claims} == {"rejected"}
    assert archive.list_graph_edges("family_1") == []

    reopened = service.reopen(
        family_id="family_1",
        conflict_id=conflict.conflict_id,
        reviewer_reference="reviewer:archivist",
        note="New family testimony requires another review.",
    )
    assert reopened.conflict.status == "open"
    assert reopened.graph_edges == 0
    assert {claim.status for claim in reopened.conflict.claims} == {"disputed"}
    assert [decision.action for decision in reopened.conflict.decisions] == [
        ConflictAction.DISMISS,
        ConflictAction.REOPEN,
    ]


def test_resolution_rejects_invalid_claim_and_cross_family_access(tmp_path: Path) -> None:
    _database, _recordings, _archive, service, _parent, _spouse, _people, conflict = _seed_conflict(
        tmp_path
    )

    with pytest.raises(ConflictResolutionError, match="must belong"):
        service.resolve(
            family_id="family_1",
            conflict_id=conflict.conflict_id,
            preferred_claim_id="claim_outside_conflict",
            reviewer_reference="reviewer:test",
            note="invalid",
        )

    with pytest.raises(ConflictNotFoundError):
        service.get_conflict(
            family_id="family_2",
            conflict_id=conflict.conflict_id,
        )
