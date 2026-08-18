from __future__ import annotations

from sqlalchemy import func, select

from mura.storage.archive import ArchiveClaimRow, ArchiveConflictRow, FamilyGraphEdgeRow
from mura.storage.conflict_resolution import (
    ConflictAction,
    ConflictMutationResult,
    ConflictNotFoundError,
    ConflictResolutionError,
    ConflictResolutionService,
    ConflictReviewView,
)
from mura.storage.database import Database, utcnow
from mura.storage.generic_claims import rebuild_materialized_profiles
from mura.storage.profile_models import (
    MaterializedPersonProfileRow,
    PersonProfileView,
    ProfileNotFoundError,
    generic_claim_is_grounded,
)


def _graph_edge_count(session, *, family_id: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(FamilyGraphEdgeRow)
            .where(FamilyGraphEdgeRow.family_id == family_id)
        )
        or 0
    )


class GenericProfileRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_profiles(self, *, family_id: str) -> list[PersonProfileView]:
        with self.database.session_factory() as session:
            rows = list(
                session.scalars(
                    select(MaterializedPersonProfileRow)
                    .where(MaterializedPersonProfileRow.family_id == family_id)
                    .order_by(MaterializedPersonProfileRow.canonical_name)
                )
            )
            return [self._view(row) for row in rows]

    def get_profile(self, *, family_id: str, person_id: str) -> PersonProfileView:
        with self.database.session_factory() as session:
            row = session.get(MaterializedPersonProfileRow, person_id)
            if row is None or row.family_id != family_id:
                raise ProfileNotFoundError("person profile not found in family archive")
            return self._view(row)

    @staticmethod
    def _view(row: MaterializedPersonProfileRow) -> PersonProfileView:
        payload = dict(row.profile_payload)
        payload["updated_at"] = row.updated_at
        return PersonProfileView.model_validate(payload)


class GenericConflictReviewService:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _get_conflict(
        session,
        *,
        family_id: str,
        conflict_id: str,
    ) -> ArchiveConflictRow:
        conflict = session.get(ArchiveConflictRow, conflict_id)
        if conflict is None or conflict.family_id != family_id:
            raise ConflictNotFoundError("conflict not found in family archive")
        if conflict.conflict_type == "relationship":
            raise ConflictResolutionError("relationship conflict must use relationship resolver")
        return conflict

    @staticmethod
    def _selectable_claim(session, claim_id: str) -> ArchiveClaimRow:
        claim = session.get(ArchiveClaimRow, claim_id)
        if claim is None or not generic_claim_is_grounded(claim):
            raise ConflictResolutionError(
                "preferred claim is not eligible for profile materialization"
            )
        return claim

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
            self._selectable_claim(session, preferred_claim_id)
            previous_status = conflict.status
            if (
                conflict.status == "resolved"
                and conflict.preferred_claim_id == preferred_claim_id
                and conflict.resolution_note == note
            ):
                rebuild_materialized_profiles(session, family_id=family_id)
                return ConflictMutationResult(
                    conflict=ConflictResolutionService._view(session, conflict),
                    graph_edges=_graph_edge_count(session, family_id=family_id),
                )
            conflict.status = "resolved"
            conflict.preferred_claim_id = preferred_claim_id
            conflict.resolution_note = note
            conflict.updated_at = utcnow()
            ConflictResolutionService._append_decision(
                session,
                conflict=conflict,
                action=ConflictAction.RESOLVE,
                previous_status=previous_status,
                resulting_status="resolved",
                reviewer_reference=reviewer_reference,
                note=note,
                preferred_claim_id=preferred_claim_id,
            )
            ConflictResolutionService._apply_conflict_state(session, conflict=conflict)
            rebuild_materialized_profiles(session, family_id=family_id)
            session.flush()
            return ConflictMutationResult(
                conflict=ConflictResolutionService._view(session, conflict),
                graph_edges=_graph_edge_count(session, family_id=family_id),
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
            previous_status = conflict.status
            if conflict.status == "dismissed" and conflict.resolution_note == note:
                rebuild_materialized_profiles(session, family_id=family_id)
                return ConflictMutationResult(
                    conflict=ConflictResolutionService._view(session, conflict),
                    graph_edges=_graph_edge_count(session, family_id=family_id),
                )
            conflict.status = "dismissed"
            conflict.preferred_claim_id = None
            conflict.resolution_note = note
            conflict.updated_at = utcnow()
            ConflictResolutionService._append_decision(
                session,
                conflict=conflict,
                action=ConflictAction.DISMISS,
                previous_status=previous_status,
                resulting_status="dismissed",
                reviewer_reference=reviewer_reference,
                note=note,
            )
            ConflictResolutionService._apply_conflict_state(session, conflict=conflict)
            rebuild_materialized_profiles(session, family_id=family_id)
            session.flush()
            return ConflictMutationResult(
                conflict=ConflictResolutionService._view(session, conflict),
                graph_edges=_graph_edge_count(session, family_id=family_id),
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
            ConflictResolutionService._append_decision(
                session,
                conflict=conflict,
                action=ConflictAction.REOPEN,
                previous_status=previous_status,
                resulting_status="open",
                reviewer_reference=reviewer_reference,
                note=note,
            )
            ConflictResolutionService._apply_conflict_state(session, conflict=conflict)
            rebuild_materialized_profiles(session, family_id=family_id)
            session.flush()
            return ConflictMutationResult(
                conflict=ConflictResolutionService._view(session, conflict),
                graph_edges=_graph_edge_count(session, family_id=family_id),
            )


class UnifiedConflictReviewService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.relationships = ConflictResolutionService(database)
        self.generic = GenericConflictReviewService(database)

    def _conflict_type(self, *, family_id: str, conflict_id: str) -> str:
        with self.database.session_factory() as session:
            conflict = session.get(ArchiveConflictRow, conflict_id)
            if conflict is None or conflict.family_id != family_id:
                raise ConflictNotFoundError("conflict not found in family archive")
            return conflict.conflict_type

    def list_conflicts(
        self,
        *,
        family_id: str,
        status: str | None = None,
    ) -> list[ConflictReviewView]:
        return self.relationships.list_conflicts(family_id=family_id, status=status)

    def get_conflict(self, *, family_id: str, conflict_id: str) -> ConflictReviewView:
        return self.relationships.get_conflict(family_id=family_id, conflict_id=conflict_id)

    def resolve(
        self,
        *,
        family_id: str,
        conflict_id: str,
        preferred_claim_id: str,
        reviewer_reference: str,
        note: str,
    ) -> ConflictMutationResult:
        if self._conflict_type(family_id=family_id, conflict_id=conflict_id) == "relationship":
            return self.relationships.resolve(
                family_id=family_id,
                conflict_id=conflict_id,
                preferred_claim_id=preferred_claim_id,
                reviewer_reference=reviewer_reference,
                note=note,
            )
        return self.generic.resolve(
            family_id=family_id,
            conflict_id=conflict_id,
            preferred_claim_id=preferred_claim_id,
            reviewer_reference=reviewer_reference,
            note=note,
        )

    def dismiss(
        self,
        *,
        family_id: str,
        conflict_id: str,
        reviewer_reference: str,
        note: str,
    ) -> ConflictMutationResult:
        if self._conflict_type(family_id=family_id, conflict_id=conflict_id) == "relationship":
            return self.relationships.dismiss(
                family_id=family_id,
                conflict_id=conflict_id,
                reviewer_reference=reviewer_reference,
                note=note,
            )
        return self.generic.dismiss(
            family_id=family_id,
            conflict_id=conflict_id,
            reviewer_reference=reviewer_reference,
            note=note,
        )

    def reopen(
        self,
        *,
        family_id: str,
        conflict_id: str,
        reviewer_reference: str,
        note: str,
    ) -> ConflictMutationResult:
        if self._conflict_type(family_id=family_id, conflict_id=conflict_id) == "relationship":
            return self.relationships.reopen(
                family_id=family_id,
                conflict_id=conflict_id,
                reviewer_reference=reviewer_reference,
                note=note,
            )
        return self.generic.reopen(
            family_id=family_id,
            conflict_id=conflict_id,
            reviewer_reference=reviewer_reference,
            note=note,
        )
