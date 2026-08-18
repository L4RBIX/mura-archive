"""Recording deletion primitives.

No user-facing endpoint exists yet -- authorization arrives in PR-03 -- but the
lifecycle work needs a correct primitive rather than an ad-hoc cascade.

Consistency, stated honestly: the database rows are removed in one transaction,
and the audio object is deleted afterwards on a best-effort, idempotent basis.
A database rollback cannot un-delete a remote object, so pretending the two are
one atomic unit would be a lie. The order is deliberate: rows first, object
second, so a crash between them leaves an orphaned object (recoverable by a
sweep) rather than a recording row pointing at bytes that no longer exist.

Family archive history deliberately survives. Claims, people, conflicts and
graph edges are family-level knowledge derived from a recording, not owned by
it; only ``pipeline_results``, ``processing_jobs`` and trace rows cascade,
which is what the existing foreign keys already express.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select

from mura.storage.audio import AudioStorage
from mura.storage.database import Database, RecordingRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecordingDeletion:
    recording_id: str
    rows_deleted: bool
    audio_deleted: bool
    audio_missing: bool


class RecordingDeletionService:
    def __init__(self, database: Database, storage: AudioStorage | None = None) -> None:
        self.database = database
        self.storage = storage

    def delete_recording(self, *, family_id: str, recording_id: str) -> RecordingDeletion:
        """Delete one recording and its derived processing rows.

        Idempotent: deleting an already-deleted recording reports no rows
        removed rather than raising, so a retried lifecycle job is safe.
        """

        storage_key: str | None = None
        with self.database.session_factory.begin() as session:
            recording = session.scalar(
                select(RecordingRow).where(
                    RecordingRow.recording_id == recording_id,
                    RecordingRow.family_id == family_id,
                )
            )
            if recording is None:
                return RecordingDeletion(
                    recording_id=recording_id,
                    rows_deleted=False,
                    audio_deleted=False,
                    audio_missing=True,
                )
            storage_key = recording.storage_key
            # processing_jobs, pipeline_results and trace events cascade from
            # this row; the family archive is intentionally left intact.
            session.execute(delete(RecordingRow).where(RecordingRow.recording_id == recording_id))

        audio_deleted = False
        audio_missing = True
        if storage_key and self.storage is not None:
            # Best effort by design: the rows are already gone, and a provider
            # outage must not resurrect them. A genuine permission or provider
            # failure still surfaces as a log line rather than silent success.
            try:
                audio_deleted = self.storage.delete(storage_key)
                audio_missing = not audio_deleted
            except Exception:
                logger.warning("audio object could not be deleted; orphan left for sweep")
                audio_missing = False

        return RecordingDeletion(
            recording_id=recording_id,
            rows_deleted=True,
            audio_deleted=audio_deleted,
            audio_missing=audio_missing,
        )
