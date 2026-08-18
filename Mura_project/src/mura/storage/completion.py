from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from mura.domain.models import PipelineResult
from mura.jobs import JobStatus
from mura.leases import LeaseOwnershipLost
from mura.observability import ProcessingTraceEvent, persist_trace_events
from mura.release_control import attach_runtime_budget
from mura.storage.database import (
    Database,
    PipelineResultRow,
    ProcessingJobRow,
    _release_lease,
    utcnow,
)


class JobFinalizationError(RuntimeError):
    pass


def finalize_recording_job(
    session: Session,
    *,
    job_id: str,
    result: PipelineResult,
    trace_events: Sequence[ProcessingTraceEvent],
    lease_owner: str | None = None,
) -> None:
    """Persist result, budget assessment, trace, and terminal job state atomically.

    Ownership is verified inside the same transaction that writes the archive,
    so a worker whose lease expired cannot overwrite the result of whichever
    worker legitimately reclaimed the recording.
    """
    now = utcnow()
    job = session.scalar(
        select(ProcessingJobRow).where(ProcessingJobRow.job_id == job_id).with_for_update()
    )
    if job is None:
        raise JobFinalizationError(f"unknown job: {job_id}")
    if job.status == JobStatus.FAILED.value:
        raise JobFinalizationError(f"cannot complete failed job: {job_id}")
    if lease_owner is not None and job.lease_owner != lease_owner:
        raise LeaseOwnershipLost(job_id)

    assessed_result = attach_runtime_budget(result, trace_events)
    payload = assessed_result.model_dump(mode="json")
    stored = session.get(PipelineResultRow, job.recording_id)
    if stored is None:
        session.add(
            PipelineResultRow(
                recording_id=job.recording_id,
                payload=payload,
            )
        )
    else:
        stored.payload = payload
        stored.updated_at = now

    persist_trace_events(session, trace_events)
    job.status = JobStatus.COMPLETED.value
    job.stage = "completed"
    job.error_code = None
    job.error_detail = None
    job.completed_at = now
    job.updated_at = now
    _release_lease(job)


def defer_recording_job(
    database: Database,
    *,
    job_id: str,
    error_code: str,
    error_detail: str,
    retry_after_seconds: float,
    trace_events: Sequence[ProcessingTraceEvent],
    lease_owner: str | None = None,
) -> None:
    now = utcnow()
    with database.session_factory.begin() as session:
        job = session.scalar(
            select(ProcessingJobRow).where(ProcessingJobRow.job_id == job_id).with_for_update()
        )
        if job is None:
            raise JobFinalizationError(f"unknown job: {job_id}")
        if lease_owner is not None and job.lease_owner != lease_owner:
            raise LeaseOwnershipLost(job_id)
        persist_trace_events(session, trace_events)
        job.status = JobStatus.QUEUED.value
        job.stage = "waiting_for_asr"
        # attempts counts claims, so the next claim increments it, not this.
        job.next_attempt_at = now + timedelta(seconds=retry_after_seconds)
        job.error_code = error_code
        job.error_detail = error_detail
        job.updated_at = now
        _release_lease(job)


def fail_recording_job(
    database: Database,
    *,
    job_id: str,
    error_code: str,
    error_detail: str,
    trace_events: Sequence[ProcessingTraceEvent],
    lease_owner: str | None = None,
) -> None:
    now = utcnow()
    with database.session_factory.begin() as session:
        job = session.scalar(
            select(ProcessingJobRow).where(ProcessingJobRow.job_id == job_id).with_for_update()
        )
        if job is None:
            raise JobFinalizationError(f"unknown job: {job_id}")
        if lease_owner is not None and job.lease_owner != lease_owner:
            raise LeaseOwnershipLost(job_id)
        persist_trace_events(session, trace_events)
        job.status = JobStatus.FAILED.value
        job.stage = "failed"
        job.error_code = error_code
        job.error_detail = error_detail
        job.completed_at = now
        job.updated_at = now
        _release_lease(job)
