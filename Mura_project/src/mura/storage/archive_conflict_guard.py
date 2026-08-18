from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from mura.domain.models import ClaimObjectType, ConflictStatus, PipelineResult
from mura.storage.archive import ArchiveClaimRow, ArchiveRepository
from mura.storage.database import RecordingRow

_INSTALL_MARKER = "_mura_conflict_guard_installed"


def _open_relationship_conflict_ids(result: PipelineResult) -> set[str]:
    return {
        conflict.conflict_id
        for conflict in result.extraction.conflict_sets
        if conflict.status is ConflictStatus.OPEN
        and any(
            reference.object_type is ClaimObjectType.RELATIONSHIP
            for reference in conflict.claim_refs
        )
    }


def install_archive_conflict_guard() -> None:
    if getattr(ArchiveRepository, _INSTALL_MARKER, False):
        return

    original_persist: Callable[..., int] = ArchiveRepository._persist_claims
    original_rebuild: Callable[..., int] = ArchiveRepository._rebuild_relationship_conflicts

    def persist_claims(
        session: Session,
        *,
        recording: RecordingRow,
        result: PipelineResult,
        mapped_people: dict[str, str],
    ) -> int:
        count = original_persist(
            session,
            recording=recording,
            result=result,
            mapped_people=mapped_people,
        )
        open_conflict_ids = _open_relationship_conflict_ids(result)
        if not open_conflict_ids:
            return count
        rows = session.scalars(
            select(ArchiveClaimRow).where(
                ArchiveClaimRow.recording_id == recording.recording_id,
                ArchiveClaimRow.object_type == ClaimObjectType.RELATIONSHIP.value,
            )
        )
        for row in rows:
            conflict_ids = set(row.payload.get("conflict_ids", []))
            if conflict_ids.intersection(open_conflict_ids) and row.status != "unresolved":
                row.status = "disputed"
        return count

    def rebuild_relationship_conflicts(session: Session, *, family_id: str) -> int:
        preserved = {
            row.claim_id
            for row in session.scalars(
                select(ArchiveClaimRow).where(
                    ArchiveClaimRow.family_id == family_id,
                    ArchiveClaimRow.object_type == ClaimObjectType.RELATIONSHIP.value,
                    ArchiveClaimRow.status == "disputed",
                )
            )
        }
        count = original_rebuild(session, family_id=family_id)
        if not preserved:
            return count
        rows = session.scalars(
            select(ArchiveClaimRow).where(ArchiveClaimRow.claim_id.in_(preserved))
        )
        for row in rows:
            if row.subject_person_id is not None and row.object_person_id is not None:
                row.status = "disputed"
        return count

    ArchiveRepository._persist_claims = staticmethod(persist_claims)  # type: ignore[method-assign]
    ArchiveRepository._rebuild_relationship_conflicts = staticmethod(  # type: ignore[method-assign]
        rebuild_relationship_conflicts
    )
    setattr(ArchiveRepository, _INSTALL_MARKER, True)
