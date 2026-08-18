from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import Field
from sqlalchemy import DateTime, ForeignKey, String, Text, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from mura.domain.models import ClaimObjectType, EvidenceClass, PipelineResult, StrictModel
from mura.storage.archive import (
    ArchiveClaimRow,
    ArchiveConflictRow,
    ArchiveRepository,
    ArchiveWriteReport,
    FamilyGraphEdgeRow,
    _edge_values,
    _mapped_people,
    _relationship_pair,
    _relationship_signature,
    _relationship_state_status,
    _stable_id,
)
from mura.storage.database import JSON_VALUE, Base, Database, RecordingRow, utcnow

_AUTO_MATERIALIZABLE_CLASSES = {
    EvidenceClass.A_EXPLICIT.value,
    EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT.value,
    EvidenceClass.C_SPEAKER_ANCHORED.value,
}


class ConflictAction(StrEnum):
    RESOLVE = "resolve"
    DISMISS = "dismiss"
    REOPEN = "reopen"
    AUTO_REOPEN = "auto_reopen"


class ArchiveConflictDecisionRow(Base):
    __tablename__ = "archive_conflict_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conflict_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("archive_conflicts.conflict_id", ondelete="CASCADE"),
        index=True,
    )
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    previous_status: Mapped[str] = mapped_column(String(32))
    resulting_status: Mapped[str] = mapped_column(String(32))
    preferred_claim_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_reference: Mapped[str] = mapped_column(String(256))
    note: Mapped[str] = mapped_column(Text)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON_VALUE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConflictClaimView(StrictModel):
    claim_id: str
    recording_id: str
    object_type: str
    predicate: str
    status: str
    evidence_class: str
    verification_status: str
    evidence_ids: list[str] = Field(default_factory=list)
    payload: dict[str, object]


class ConflictDecisionView(StrictModel):
    decision_id: str
    action: ConflictAction
    previous_status: str
    resulting_status: str
    preferred_claim_id: str | None = None
    reviewer_reference: str
    note: str
    metadata_payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class ConflictReviewView(StrictModel):
    conflict_id: str
    family_id: str
    conflict_type: str
    status: str
    detected_by: str
    claim_ids: list[str]
    preferred_claim_id: str | None = None
    rationale: str
    resolution_note: str | None = None
    created_at: datetime
    updated_at: datetime
    claims: list[ConflictClaimView] = Field(default_factory=list)
    decisions: list[ConflictDecisionView] = Field(default_factory=list)


class ConflictMutationResult(StrictModel):
    conflict: ConflictReviewView
    graph_edges: int = Field(ge=0)


class ConflictResolutionError(ValueError):
    pass


class ConflictNotFoundError(LookupError):
    pass


def _decision_id() -> str:
    return f"decision_{uuid.uuid4().hex}"


def _claim_is_grounded(claim: ArchiveClaimRow) -> bool:
    return (
        _relationship_state_status(claim) == "active"
        and claim.subject_person_id is not None
        and claim.object_person_id is not None
        and claim.subject_person_id != claim.object_person_id
        and claim.evidence_class in _AUTO_MATERIALIZABLE_CLASSES
        and bool(claim.evidence_ids)
    )


def _base_claim_status(claim: ArchiveClaimRow) -> str:
    return _relationship_state_status(claim)


class ConflictResolutionService:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def persist_pipeline_result(
        session: Session,
        *,
        recording: RecordingRow,
        result: PipelineResult,
    ) -> ArchiveWriteReport:
        mapped_people = _mapped_people(result)
        people_upserted = ArchiveRepository._upsert_people(
            session,
            recording=recording,
            result=result,
            mapped_people=mapped_people,
        )
        claims_persisted = ArchiveRepository._persist_claims(
            session,
            recording=recording,
            result=result,
            mapped_people=mapped_people,
        )
        corrections_persisted = ArchiveRepository._persist_corrections(
            session,
            recording=recording,
            result=result,
        )
        open_conflicts = ConflictResolutionService._reconcile_relationship_conflicts(
            session,
            family_id=recording.family_id,
        )
        graph_edges = ConflictResolutionService._rebuild_graph(
            session,
            family_id=recording.family_id,
        )
        return ArchiveWriteReport(
            people_upserted=people_upserted,
            claims_persisted=claims_persisted,
            corrections_persisted=corrections_persisted,
            open_conflicts=open_conflicts,
            graph_edges=graph_edges,
        )

    @staticmethod
    def _relationship_claims(
        session: Session,
        *,
        family_id: str,
    ) -> list[ArchiveClaimRow]:
        return list(
            session.scalars(
                select(ArchiveClaimRow).where(
                    ArchiveClaimRow.family_id == family_id,
                    ArchiveClaimRow.object_type == ClaimObjectType.RELATIONSHIP.value,
                )
            )
        )

    @staticmethod
    def _conflict_pair(
        session: Session,
        conflict: ArchiveConflictRow,
    ) -> tuple[str, str] | None:
        for claim_id in conflict.claim_ids:
            claim = session.get(ArchiveClaimRow, claim_id)
            if claim is not None and claim.object_type == ClaimObjectType.RELATIONSHIP.value:
                return _relationship_pair(claim)
        return None

    @staticmethod
    def _find_existing_conflict(
        session: Session,
        *,
        family_id: str,
        pair: tuple[str, str],
        claim_ids: list[str],
    ) -> ArchiveConflictRow | None:
        conflicts = list(
            session.scalars(
                select(ArchiveConflictRow)
                .where(
                    ArchiveConflictRow.family_id == family_id,
                    ArchiveConflictRow.conflict_type == "relationship",
                )
                .order_by(ArchiveConflictRow.updated_at.desc())
            )
        )
        exact = next(
            (item for item in conflicts if set(item.claim_ids) == set(claim_ids)),
            None,
        )
        if exact is not None:
            return exact
        return next(
            (
                item
                for item in conflicts
                if ConflictResolutionService._conflict_pair(session, item) == pair
            ),
            None,
        )

    @staticmethod
    def _append_decision(
        session: Session,
        *,
        conflict: ArchiveConflictRow,
        action: ConflictAction,
        previous_status: str,
        resulting_status: str,
        reviewer_reference: str,
        note: str,
        preferred_claim_id: str | None = None,
        metadata_payload: dict[str, object] | None = None,
    ) -> None:
        session.add(
            ArchiveConflictDecisionRow(
                decision_id=_decision_id(),
                conflict_id=conflict.conflict_id,
                family_id=conflict.family_id,
                action=action.value,
                previous_status=previous_status,
                resulting_status=resulting_status,
                preferred_claim_id=preferred_claim_id,
                reviewer_reference=reviewer_reference,
                note=note,
                metadata_payload=metadata_payload or {},
            )
        )

    @staticmethod
    def _apply_conflict_state(
        session: Session,
        *,
        conflict: ArchiveConflictRow,
    ) -> None:
        claims = [session.get(ArchiveClaimRow, claim_id) for claim_id in conflict.claim_ids]
        available = [claim for claim in claims if claim is not None]
        if conflict.status == "resolved":
            for claim in available:
                claim.status = (
                    "accepted" if claim.claim_id == conflict.preferred_claim_id else "rejected"
                )
        elif conflict.status == "dismissed":
            for claim in available:
                claim.status = "rejected"
        else:
            for claim in available:
                claim.status = "disputed"

    @staticmethod
    def _reconcile_relationship_conflicts(session: Session, *, family_id: str) -> int:
        claims = ConflictResolutionService._relationship_claims(
            session,
            family_id=family_id,
        )
        for claim in claims:
            claim.status = _base_claim_status(claim)

        eligible = [claim for claim in claims if _claim_is_grounded(claim)]
        grouped: dict[tuple[str, str], list[ArchiveClaimRow]] = {}
        for claim in eligible:
            grouped.setdefault(_relationship_pair(claim), []).append(claim)

        current_conflicts: list[ArchiveConflictRow] = []
        for pair, candidates in grouped.items():
            signatures = {_relationship_signature(candidate) for candidate in candidates}
            if len(signatures) <= 1:
                continue

            claim_ids = sorted(candidate.claim_id for candidate in candidates)
            conflict = ConflictResolutionService._find_existing_conflict(
                session,
                family_id=family_id,
                pair=pair,
                claim_ids=claim_ids,
            )
            if conflict is None:
                conflict = ArchiveConflictRow(
                    conflict_id=_stable_id("conflict", family_id, *claim_ids),
                    family_id=family_id,
                    conflict_type="relationship",
                    status="open",
                    detected_by="deterministic",
                    claim_ids=claim_ids,
                    rationale=(
                        "grounded relationship claims disagree for archive people "
                        f"{pair[0]} and {pair[1]}"
                    ),
                )
                session.add(conflict)
                session.flush()
            elif set(conflict.claim_ids) != set(claim_ids):
                previous_status = conflict.status
                previous_claim_ids = list(conflict.claim_ids)
                conflict.claim_ids = claim_ids
                conflict.status = "open"
                conflict.preferred_claim_id = None
                conflict.resolution_note = None
                conflict.updated_at = utcnow()
                ConflictResolutionService._append_decision(
                    session,
                    conflict=conflict,
                    action=ConflictAction.AUTO_REOPEN,
                    previous_status=previous_status,
                    resulting_status="open",
                    reviewer_reference="system:archive-ingestion",
                    note="conflict reopened because its competing claim set changed",
                    metadata_payload={
                        "previous_claim_ids": previous_claim_ids,
                        "current_claim_ids": claim_ids,
                    },
                )
            elif conflict.status == "resolved" and conflict.preferred_claim_id not in claim_ids:
                previous_status = conflict.status
                conflict.status = "open"
                conflict.preferred_claim_id = None
                conflict.resolution_note = None
                conflict.updated_at = utcnow()
                ConflictResolutionService._append_decision(
                    session,
                    conflict=conflict,
                    action=ConflictAction.AUTO_REOPEN,
                    previous_status=previous_status,
                    resulting_status="open",
                    reviewer_reference="system:archive-ingestion",
                    note="conflict reopened because the preferred claim is unavailable",
                )

            ConflictResolutionService._apply_conflict_state(session, conflict=conflict)
            current_conflicts.append(conflict)

        return sum(conflict.status == "open" for conflict in current_conflicts)

    @staticmethod
    def _rebuild_graph(session: Session, *, family_id: str) -> int:
        session.execute(delete(FamilyGraphEdgeRow).where(FamilyGraphEdgeRow.family_id == family_id))
        claims = ConflictResolutionService._relationship_claims(
            session,
            family_id=family_id,
        )
        eligible = [
            claim
            for claim in claims
            if claim.status in {"active", "accepted"} and _claim_is_grounded(claim)
        ]
        grouped: dict[tuple[str, str, str, str, str], list[ArchiveClaimRow]] = {}
        for claim in eligible:
            grouped.setdefault(_edge_values(claim), []).append(claim)

        for values, sources in grouped.items():
            relationship_type, subject_id, subject_role, object_id, object_role = values
            session.add(
                FamilyGraphEdgeRow(
                    edge_id=_stable_id("edge", family_id, *values),
                    family_id=family_id,
                    relationship_type=relationship_type,
                    subject_person_id=subject_id,
                    subject_role=subject_role,
                    object_person_id=object_id,
                    object_role=object_role,
                    source_claim_ids=sorted(source.claim_id for source in sources),
                )
            )
        return len(grouped)

    @staticmethod
    def _get_conflict(
        session: Session,
        *,
        family_id: str,
        conflict_id: str,
    ) -> ArchiveConflictRow:
        conflict = session.get(ArchiveConflictRow, conflict_id)
        if conflict is None or conflict.family_id != family_id:
            raise ConflictNotFoundError("conflict not found in family archive")
        return conflict

    def resolve(
        self,
        *,
        family_id: str,
        conflict_id: str,
        preferred_claim_id: str,
        reviewer_reference: str,
        note: str,
    ) -> ConflictMutationResult:
        with self.database.session_factory.begin() as session:
            conflict = self._get_conflict(
                session,
                family_id=family_id,
                conflict_id=conflict_id,
            )
            if preferred_claim_id not in conflict.claim_ids:
                raise ConflictResolutionError("preferred claim must belong to the conflict")
            preferred = session.get(ArchiveClaimRow, preferred_claim_id)
            if preferred is None or not _claim_is_grounded(preferred):
                raise ConflictResolutionError("preferred claim is not eligible for materialization")
            if (
                conflict.status == "resolved"
                and conflict.preferred_claim_id == preferred_claim_id
                and conflict.resolution_note == note
            ):
                graph_edges = self._rebuild_graph(session, family_id=family_id)
                session.flush()
                return ConflictMutationResult(
                    conflict=self._view(session, conflict),
                    graph_edges=graph_edges,
                )

            previous_status = conflict.status
            conflict.status = "resolved"
            conflict.preferred_claim_id = preferred_claim_id
            conflict.resolution_note = note
            conflict.updated_at = utcnow()
            self._append_decision(
                session,
                conflict=conflict,
                action=ConflictAction.RESOLVE,
                previous_status=previous_status,
                resulting_status="resolved",
                reviewer_reference=reviewer_reference,
                note=note,
                preferred_claim_id=preferred_claim_id,
            )
            self._apply_conflict_state(session, conflict=conflict)
            graph_edges = self._rebuild_graph(session, family_id=family_id)
            session.flush()
            return ConflictMutationResult(
                conflict=self._view(session, conflict),
                graph_edges=graph_edges,
            )

    def dismiss(
        self,
        *,
        family_id: str,
        conflict_id: str,
        reviewer_reference: str,
        note: str,
    ) -> ConflictMutationResult:
        with self.database.session_factory.begin() as session:
            conflict = self._get_conflict(
                session,
                family_id=family_id,
                conflict_id=conflict_id,
            )
            if conflict.status == "dismissed" and conflict.resolution_note == note:
                graph_edges = self._rebuild_graph(session, family_id=family_id)
                session.flush()
                return ConflictMutationResult(
                    conflict=self._view(session, conflict),
                    graph_edges=graph_edges,
                )

            previous_status = conflict.status
            conflict.status = "dismissed"
            conflict.preferred_claim_id = None
            conflict.resolution_note = note
            conflict.updated_at = utcnow()
            self._append_decision(
                session,
                conflict=conflict,
                action=ConflictAction.DISMISS,
                previous_status=previous_status,
                resulting_status="dismissed",
                reviewer_reference=reviewer_reference,
                note=note,
            )
            self._apply_conflict_state(session, conflict=conflict)
            graph_edges = self._rebuild_graph(session, family_id=family_id)
            session.flush()
            return ConflictMutationResult(
                conflict=self._view(session, conflict),
                graph_edges=graph_edges,
            )

    def reopen(
        self,
        *,
        family_id: str,
        conflict_id: str,
        reviewer_reference: str,
        note: str,
    ) -> ConflictMutationResult:
        with self.database.session_factory.begin() as session:
            conflict = self._get_conflict(
                session,
                family_id=family_id,
                conflict_id=conflict_id,
            )
            if conflict.status == "open":
                raise ConflictResolutionError("conflict is already open")

            previous_status = conflict.status
            conflict.status = "open"
            conflict.preferred_claim_id = None
            conflict.resolution_note = note
            conflict.updated_at = utcnow()
            self._append_decision(
                session,
                conflict=conflict,
                action=ConflictAction.REOPEN,
                previous_status=previous_status,
                resulting_status="open",
                reviewer_reference=reviewer_reference,
                note=note,
            )
            self._apply_conflict_state(session, conflict=conflict)
            graph_edges = self._rebuild_graph(session, family_id=family_id)
            session.flush()
            return ConflictMutationResult(
                conflict=self._view(session, conflict),
                graph_edges=graph_edges,
            )

    def list_conflicts(
        self,
        *,
        family_id: str,
        status: str | None = None,
    ) -> list[ConflictReviewView]:
        with self.database.session_factory() as session:
            statement = select(ArchiveConflictRow).where(ArchiveConflictRow.family_id == family_id)
            if status is not None:
                statement = statement.where(ArchiveConflictRow.status == status)
            conflicts = list(
                session.scalars(statement.order_by(ArchiveConflictRow.updated_at.desc()))
            )
            return [self._view(session, conflict) for conflict in conflicts]

    def get_conflict(self, *, family_id: str, conflict_id: str) -> ConflictReviewView:
        with self.database.session_factory() as session:
            conflict = self._get_conflict(
                session,
                family_id=family_id,
                conflict_id=conflict_id,
            )
            return self._view(session, conflict)

    @staticmethod
    def _view(session: Session, conflict: ArchiveConflictRow) -> ConflictReviewView:
        claims = [session.get(ArchiveClaimRow, claim_id) for claim_id in conflict.claim_ids]
        claim_views = [
            ConflictClaimView(
                claim_id=claim.claim_id,
                recording_id=claim.recording_id,
                object_type=claim.object_type,
                predicate=claim.predicate,
                status=claim.status,
                evidence_class=claim.evidence_class,
                verification_status=claim.verification_status,
                evidence_ids=list(claim.evidence_ids),
                payload=dict(claim.payload),
            )
            for claim in claims
            if claim is not None
        ]
        decisions = list(
            session.scalars(
                select(ArchiveConflictDecisionRow)
                .where(ArchiveConflictDecisionRow.conflict_id == conflict.conflict_id)
                .order_by(ArchiveConflictDecisionRow.created_at)
            )
        )
        decision_views = [
            ConflictDecisionView(
                decision_id=decision.decision_id,
                action=ConflictAction(decision.action),
                previous_status=decision.previous_status,
                resulting_status=decision.resulting_status,
                preferred_claim_id=decision.preferred_claim_id,
                reviewer_reference=decision.reviewer_reference,
                note=decision.note,
                metadata_payload=dict(decision.metadata_payload),
                created_at=decision.created_at,
            )
            for decision in decisions
        ]
        return ConflictReviewView(
            conflict_id=conflict.conflict_id,
            family_id=conflict.family_id,
            conflict_type=conflict.conflict_type,
            status=conflict.status,
            detected_by=conflict.detected_by,
            claim_ids=list(conflict.claim_ids),
            preferred_claim_id=conflict.preferred_claim_id,
            rationale=conflict.rationale,
            resolution_note=conflict.resolution_note,
            created_at=conflict.created_at,
            updated_at=conflict.updated_at,
            claims=claim_views,
            decisions=decision_views,
        )
