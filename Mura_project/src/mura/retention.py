from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import Field
from sqlalchemy import delete, select

from mura.domain.models import StrictModel
from mura.jobs import JobStatus
from mura.observability import ProcessingTraceEventRow
from mura.replay import PipelineReplayRunRow
from mura.storage.database import Database, ProcessingJobRow

RETENTION_CONFIRMATION = "DELETE_EXPIRED_OPERATIONAL_DATA"


class RetentionPolicy(StrictModel):
    schema_version: str = "operational-retention-v1"
    trace_retention_days: int = Field(default=30, ge=1, le=3650)
    replay_retention_days: int = Field(default=90, ge=1, le=3650)
    preserve_family_archive: bool = True
    preserve_pipeline_results: bool = True
    preserve_release_audit: bool = True


class RetentionReport(StrictModel):
    schema_version: str = "retention-report-v1"
    applied: bool
    trace_cutoff: datetime
    replay_cutoff: datetime
    expired_trace_events: int = Field(ge=0)
    expired_replay_runs: int = Field(ge=0)
    deleted_trace_events: int = Field(ge=0)
    deleted_replay_runs: int = Field(ge=0)
    policy: RetentionPolicy
    preserved_data: list[str] = Field(default_factory=list)


class RetentionConfirmationError(ValueError):
    pass


class RetentionService:
    def __init__(self, database: Database, policy: RetentionPolicy | None = None) -> None:
        self.database = database
        self.policy = policy or RetentionPolicy()

    def preview(self, *, now: datetime | None = None) -> RetentionReport:
        resolved_now = now or datetime.now(UTC)
        trace_cutoff = resolved_now - timedelta(days=self.policy.trace_retention_days)
        replay_cutoff = resolved_now - timedelta(days=self.policy.replay_retention_days)
        with self.database.session_factory() as session:
            terminal_job_ids = select(ProcessingJobRow.job_id).where(
                ProcessingJobRow.status.in_([JobStatus.COMPLETED.value, JobStatus.FAILED.value]),
                ProcessingJobRow.completed_at.is_not(None),
                ProcessingJobRow.completed_at < trace_cutoff,
            )
            trace_ids = list(
                session.scalars(
                    select(ProcessingTraceEventRow.event_id).where(
                        ProcessingTraceEventRow.job_id.in_(terminal_job_ids),
                        ProcessingTraceEventRow.created_at < trace_cutoff,
                    )
                )
            )
            replay_ids = list(
                session.scalars(
                    select(PipelineReplayRunRow.replay_id).where(
                        PipelineReplayRunRow.created_at < replay_cutoff
                    )
                )
            )
        return RetentionReport(
            applied=False,
            trace_cutoff=trace_cutoff,
            replay_cutoff=replay_cutoff,
            expired_trace_events=len(trace_ids),
            expired_replay_runs=len(replay_ids),
            deleted_trace_events=0,
            deleted_replay_runs=0,
            policy=self.policy,
            preserved_data=[
                "recordings",
                "audio_paths",
                "pipeline_results",
                "archive_people",
                "archive_claims",
                "archive_conflicts",
                "archive_conflict_decisions",
                "family_graph_edges",
                "materialized_person_profiles",
                "release_decisions",
            ],
        )

    def apply(
        self,
        *,
        confirmation: str,
        now: datetime | None = None,
    ) -> RetentionReport:
        if confirmation != RETENTION_CONFIRMATION:
            raise RetentionConfirmationError(f"confirmation must equal {RETENTION_CONFIRMATION!r}")
        preview = self.preview(now=now)
        with self.database.session_factory.begin() as session:
            terminal_job_ids = select(ProcessingJobRow.job_id).where(
                ProcessingJobRow.status.in_([JobStatus.COMPLETED.value, JobStatus.FAILED.value]),
                ProcessingJobRow.completed_at.is_not(None),
                ProcessingJobRow.completed_at < preview.trace_cutoff,
            )
            trace_result = session.execute(
                delete(ProcessingTraceEventRow).where(
                    ProcessingTraceEventRow.job_id.in_(terminal_job_ids),
                    ProcessingTraceEventRow.created_at < preview.trace_cutoff,
                )
            )
            replay_result = session.execute(
                delete(PipelineReplayRunRow).where(
                    PipelineReplayRunRow.created_at < preview.replay_cutoff
                )
            )
            deleted_trace_events = max(0, int(getattr(trace_result, "rowcount", 0) or 0))
            deleted_replay_runs = max(0, int(getattr(replay_result, "rowcount", 0) or 0))
        return preview.model_copy(
            update={
                "applied": True,
                "deleted_trace_events": deleted_trace_events,
                "deleted_replay_runs": deleted_replay_runs,
            }
        )
