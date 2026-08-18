from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import Field
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from mura.domain.models import ExtractionResult, PipelineResult, StrictModel
from mura.extraction_sanitizer import sanitize_extraction_output
from mura.release_control import CURRENT_RELEASE_ID
from mura.storage.archive import (
    ArchiveClaimRow,
    ArchiveConflictRow,
    ArchiveCorrectionRow,
    ArchivePersonRow,
    FamilyGraphEdgeRow,
)
from mura.storage.conflict_resolution import ConflictResolutionService
from mura.storage.database import (
    JSON_VALUE,
    Base,
    Database,
    PipelineResultRow,
    RecordingRow,
    utcnow,
)
from mura.storage.generic_claims import persist_generic_claims
from mura.storage.profile_models import MaterializedPersonProfileRow

REPLAY_PROTOCOL_VERSION = "deterministic-family-replay-v1"
SEMANTIC_EXTRACTION_SCOPE = "semantic-extraction-v1-without-provenance-activities"


class PipelineReplayRunRow(Base):
    __tablename__ = "pipeline_replay_runs"

    replay_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    release_id: Mapped[str] = mapped_column(String(96), index=True)
    protocol_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    source_recording_count: Mapped[int] = mapped_column(Integer)
    issue_count: Mapped[int] = mapped_column(Integer)
    input_hash: Mapped[str] = mapped_column(String(64))
    output_hash: Mapped[str] = mapped_column(String(64))
    report_payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecordingReplayResult(StrictModel):
    recording_id: str
    comparison_scope: str = SEMANTIC_EXTRACTION_SCOPE
    source_extraction_hash: str
    replayed_extraction_hash: str
    extraction_matches: bool
    provenance_activity_count: int = Field(ge=0)
    sanitizer_issue_count: int = Field(ge=0)
    evidence_closure_count: int = Field(ge=0)
    sanitizer_issues: list[dict[str, Any]] = Field(default_factory=list)


class FamilyReplayReport(StrictModel):
    schema_version: str = "family-replay-report-v1"
    replay_id: str
    family_id: str
    release_id: str = CURRENT_RELEASE_ID
    protocol_version: str = REPLAY_PROTOCOL_VERSION
    status: str
    source_recording_count: int = Field(ge=0)
    input_hash: str
    output_hash: str
    snapshot_counts: dict[str, int]
    recording_results: list[RecordingReplayResult]
    issue_count: int = Field(ge=0)
    human_decisions_replayed: bool = False
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class ReplayNotFoundError(LookupError):
    pass


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _semantic_extraction_payload(extraction: ExtractionResult) -> dict[str, Any]:
    payload = extraction.model_dump(mode="json")
    payload.pop("provenance_activities", None)
    return payload


def _candidate_payload_for_replay(extraction: ExtractionResult) -> dict[str, Any]:
    payload = extraction.model_dump(mode="json")
    payload["provenance_activities"] = []
    return payload


def _snapshot(session: Session, *, family_id: str) -> dict[str, object]:
    people = [
        {
            "person_id": row.person_id,
            "canonical_name": row.canonical_name,
            "normalized_name": row.normalized_name,
            "aliases": sorted(row.aliases),
            "verified_aliases": sorted(row.verified_aliases),
            "category": row.category,
            "relations_to_speakers": row.relations_to_speakers,
            "source_recording_ids": sorted(row.source_recording_ids),
        }
        for row in session.scalars(
            select(ArchivePersonRow)
            .where(ArchivePersonRow.family_id == family_id)
            .order_by(ArchivePersonRow.person_id)
        )
    ]
    claims = [
        {
            "claim_id": row.claim_id,
            "recording_id": row.recording_id,
            "object_type": row.object_type,
            "source_object_id": row.source_object_id,
            "predicate": row.predicate,
            "subject_person_id": row.subject_person_id,
            "object_person_id": row.object_person_id,
            "payload": row.payload,
            "evidence_ids": sorted(row.evidence_ids),
            "evidence_class": row.evidence_class,
            "verification_status": row.verification_status,
            "assertion_mode": row.assertion_mode,
            "status": row.status,
            "derived_from_claim_ids": sorted(row.derived_from_claim_ids),
        }
        for row in session.scalars(
            select(ArchiveClaimRow)
            .where(ArchiveClaimRow.family_id == family_id)
            .order_by(ArchiveClaimRow.claim_id)
        )
    ]
    conflicts = [
        {
            "conflict_id": row.conflict_id,
            "conflict_type": row.conflict_type,
            "status": row.status,
            "detected_by": row.detected_by,
            "claim_ids": sorted(row.claim_ids),
            "preferred_claim_id": row.preferred_claim_id,
            "rationale": row.rationale,
            "resolution_note": row.resolution_note,
        }
        for row in session.scalars(
            select(ArchiveConflictRow)
            .where(ArchiveConflictRow.family_id == family_id)
            .order_by(ArchiveConflictRow.conflict_id)
        )
    ]
    edges = [
        {
            "edge_id": row.edge_id,
            "relationship_type": row.relationship_type,
            "subject_person_id": row.subject_person_id,
            "subject_role": row.subject_role,
            "object_person_id": row.object_person_id,
            "object_role": row.object_role,
            "source_claim_ids": sorted(row.source_claim_ids),
        }
        for row in session.scalars(
            select(FamilyGraphEdgeRow)
            .where(FamilyGraphEdgeRow.family_id == family_id)
            .order_by(FamilyGraphEdgeRow.edge_id)
        )
    ]
    corrections = [
        {
            "correction_id": row.correction_id,
            "recording_id": row.recording_id,
            "kind": row.kind,
            "subject": row.subject,
            "original_value": row.original_value,
            "corrected_value": row.corrected_value,
            "source_segment_ids": sorted(row.source_segment_ids),
            "explanation": row.explanation,
            "confidence": row.confidence,
        }
        for row in session.scalars(
            select(ArchiveCorrectionRow)
            .where(ArchiveCorrectionRow.family_id == family_id)
            .order_by(ArchiveCorrectionRow.correction_id)
        )
    ]
    profiles = [
        {
            "person_id": row.person_id,
            "canonical_name": row.canonical_name,
            "profile_payload": row.profile_payload,
            "source_claim_ids": sorted(row.source_claim_ids),
        }
        for row in session.scalars(
            select(MaterializedPersonProfileRow)
            .where(MaterializedPersonProfileRow.family_id == family_id)
            .order_by(MaterializedPersonProfileRow.person_id)
        )
    ]
    return {
        "people": people,
        "claims": claims,
        "conflicts": conflicts,
        "edges": edges,
        "corrections": corrections,
        "profiles": profiles,
    }


class FamilyReplayService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self, *, family_id: str) -> FamilyReplayReport:
        with self.database.session_factory() as session:
            source_rows = list(
                session.execute(
                    select(RecordingRow, PipelineResultRow)
                    .join(
                        PipelineResultRow,
                        PipelineResultRow.recording_id == RecordingRow.recording_id,
                    )
                    .where(RecordingRow.family_id == family_id)
                    .order_by(RecordingRow.created_at, RecordingRow.recording_id)
                ).all()
            )
        if not source_rows:
            raise ReplayNotFoundError(f"family has no completed recordings: {family_id}")

        source_payloads = [result_row.payload for _, result_row in source_rows]
        input_hash = _hash(source_payloads)
        shadow = Database("sqlite+pysqlite:///:memory:")
        shadow.create_schema()
        recording_results: list[RecordingReplayResult] = []

        for recording, result_row in source_rows:
            source_result = PipelineResult.model_validate(result_row.payload)
            sanitized, sanitizer_issues, closure_count = sanitize_extraction_output(
                raw=_candidate_payload_for_replay(source_result.extraction),
                transcript=source_result.transcript,
                speaker_id=source_result.extraction.speaker_id,
                speaker_name=source_result.extraction.speaker_name,
            )
            source_extraction_hash = _hash(_semantic_extraction_payload(source_result.extraction))
            replayed_extraction_hash = _hash(_semantic_extraction_payload(sanitized))
            recording_results.append(
                RecordingReplayResult(
                    recording_id=recording.recording_id,
                    source_extraction_hash=source_extraction_hash,
                    replayed_extraction_hash=replayed_extraction_hash,
                    extraction_matches=source_extraction_hash == replayed_extraction_hash,
                    provenance_activity_count=len(sanitized.provenance_activities),
                    sanitizer_issue_count=len(sanitizer_issues),
                    evidence_closure_count=closure_count,
                    sanitizer_issues=sanitizer_issues,
                )
            )
            replayed_result = source_result.model_copy(update={"extraction": sanitized})
            with shadow.session_factory.begin() as shadow_session:
                shadow_recording = RecordingRow(
                    recording_id=recording.recording_id,
                    family_id=recording.family_id,
                    speaker_id=recording.speaker_id,
                    speaker_name=recording.speaker_name,
                    original_filename=recording.original_filename,
                    content_type=recording.content_type,
                    # Storage key when present, legacy locator otherwise.
                    audio_path=recording.storage_key or recording.audio_path,
                    created_at=recording.created_at,
                )
                shadow_session.add(shadow_recording)
                shadow_session.flush()
                ConflictResolutionService.persist_pipeline_result(
                    shadow_session,
                    recording=shadow_recording,
                    result=replayed_result,
                )
                persist_generic_claims(
                    shadow_session,
                    recording=shadow_recording,
                    result=replayed_result,
                )

        with shadow.session_factory() as shadow_session:
            snapshot = _snapshot(shadow_session, family_id=family_id)
        output_hash = _hash(snapshot)
        issue_count = sum(item.sanitizer_issue_count for item in recording_results)
        extraction_matches = all(item.extraction_matches for item in recording_results)
        status = "passed" if issue_count == 0 and extraction_matches else "failed"
        counts = {
            name: len(values) if isinstance(values, list) else 0
            for name, values in snapshot.items()
        }
        report = FamilyReplayReport(
            replay_id=f"replay_{uuid.uuid4().hex}",
            family_id=family_id,
            status=status,
            source_recording_count=len(source_rows),
            input_hash=input_hash,
            output_hash=output_hash,
            snapshot_counts=counts,
            recording_results=recording_results,
            issue_count=issue_count,
            notes=[
                "Replay uses stored immutable transcripts, extraction candidates, and resolutions.",
                "No ASR or LLM provider is called.",
                "Authoritative run provenance is rebuilt rather than treated as a model candidate.",
                "Semantic hashes exclude run provenance; evidence and facts remain included.",
                "Human conflict decisions are not replayed into the shadow materialization.",
            ],
        )
        with self.database.session_factory.begin() as session:
            session.add(
                PipelineReplayRunRow(
                    replay_id=report.replay_id,
                    family_id=family_id,
                    release_id=report.release_id,
                    protocol_version=report.protocol_version,
                    status=report.status,
                    source_recording_count=report.source_recording_count,
                    issue_count=report.issue_count,
                    input_hash=report.input_hash,
                    output_hash=report.output_hash,
                    report_payload=report.model_dump(mode="json"),
                    created_at=report.created_at,
                )
            )
        return report

    def list_runs(self, *, family_id: str, limit: int = 20) -> list[FamilyReplayReport]:
        with self.database.session_factory() as session:
            rows = list(
                session.scalars(
                    select(PipelineReplayRunRow)
                    .where(PipelineReplayRunRow.family_id == family_id)
                    .order_by(PipelineReplayRunRow.created_at.desc())
                    .limit(limit)
                )
            )
        return [FamilyReplayReport.model_validate(row.report_payload) for row in rows]
