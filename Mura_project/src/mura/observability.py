from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from mura.domain.models import StrictModel
from mura.storage.database import JSON_VALUE, Base, Database, utcnow

TRACE_SCHEMA_VERSION = "processing-trace-v1"
COMPLETION_PROTOCOL_VERSION = "archive-job-atomic-v1"

TraceScalar = str | int | float | bool | None
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "audio_path",
    "authorization",
    "body",
    "name",
    "prompt",
    "secret",
    "text",
    "token",
    "transcript",
)


class TraceOutcome(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    DEFERRED = "deferred"
    ERROR = "error"


class ProcessingTraceEventRow(Base):
    __tablename__ = "processing_trace_events"
    __table_args__ = (
        UniqueConstraint(
            "trace_id",
            "attempt",
            "sequence",
            name="uq_processing_trace_attempt_sequence",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(96), index=True)
    job_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("processing_jobs.job_id", ondelete="CASCADE"),
        index=True,
    )
    recording_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("recordings.recording_id", ondelete="CASCADE"),
        index=True,
    )
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(64), index=True)
    event_name: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attributes: Mapped[dict[str, TraceScalar]] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessingTraceEvent(StrictModel):
    schema_version: str = TRACE_SCHEMA_VERSION
    event_id: str = Field(min_length=1, max_length=64)
    trace_id: str = Field(min_length=1, max_length=96)
    job_id: str = Field(min_length=1, max_length=64)
    recording_id: str = Field(min_length=1, max_length=64)
    family_id: str = Field(min_length=1, max_length=128)
    attempt: int = Field(ge=1)
    sequence: int = Field(ge=1)
    stage: str = Field(min_length=1, max_length=64)
    event_name: str = Field(min_length=1, max_length=64)
    outcome: TraceOutcome
    duration_ms: int | None = Field(default=None, ge=0)
    attributes: dict[str, TraceScalar] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class JobTraceView(StrictModel):
    schema_version: str = TRACE_SCHEMA_VERSION
    trace_id: str
    job_id: str
    recording_id: str
    family_id: str
    attempts: list[int]
    total_duration_ms: int
    stage_durations_ms: dict[str, int]
    events: list[ProcessingTraceEvent]


def sanitize_trace_attributes(
    attributes: Mapping[str, TraceScalar] | None,
) -> dict[str, TraceScalar]:
    if not attributes:
        return {}
    sanitized: dict[str, TraceScalar] = {}
    for raw_key, raw_value in attributes.items():
        key = str(raw_key).strip().lower()[:64]
        if not key or any(part in key for part in _SENSITIVE_KEY_PARTS):
            continue
        if isinstance(raw_value, str):
            sanitized[key] = raw_value[:256]
        elif raw_value is None or isinstance(raw_value, (bool, int, float)):
            sanitized[key] = raw_value
    return sanitized


class ProcessingTrace:
    def __init__(
        self,
        *,
        job_id: str,
        recording_id: str,
        family_id: str,
        attempt: int,
    ) -> None:
        self.trace_id = f"trace_{job_id.removeprefix('job_')}"
        self.job_id = job_id
        self.recording_id = recording_id
        self.family_id = family_id
        self.attempt = attempt
        self._sequence = 0
        self._started: dict[str, float] = {}
        self._events: list[ProcessingTraceEvent] = []

    @property
    def events(self) -> list[ProcessingTraceEvent]:
        return list(self._events)

    def start(self, stage: str) -> None:
        if stage in self._started:
            raise RuntimeError(f"trace stage already started: {stage}")
        self._started[stage] = time.perf_counter()

    def finish(
        self,
        stage: str,
        *,
        outcome: TraceOutcome,
        event_name: str = "stage_completed",
        attributes: Mapping[str, TraceScalar] | None = None,
    ) -> ProcessingTraceEvent:
        started = self._started.pop(stage, None)
        if started is None:
            raise RuntimeError(f"trace stage was not started: {stage}")
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        return self.instant(
            stage=stage,
            event_name=event_name,
            outcome=outcome,
            duration_ms=duration_ms,
            attributes=attributes,
        )

    def instant(
        self,
        *,
        stage: str,
        event_name: str,
        outcome: TraceOutcome = TraceOutcome.INFO,
        duration_ms: int | None = None,
        attributes: Mapping[str, TraceScalar] | None = None,
    ) -> ProcessingTraceEvent:
        self._sequence += 1
        event_id = _event_id(
            trace_id=self.trace_id,
            attempt=self.attempt,
            sequence=self._sequence,
            stage=stage,
            event_name=event_name,
        )
        event = ProcessingTraceEvent(
            event_id=event_id,
            trace_id=self.trace_id,
            job_id=self.job_id,
            recording_id=self.recording_id,
            family_id=self.family_id,
            attempt=self.attempt,
            sequence=self._sequence,
            stage=stage,
            event_name=event_name,
            outcome=outcome,
            duration_ms=duration_ms,
            attributes=sanitize_trace_attributes(attributes),
        )
        self._events.append(event)
        return event

    def fail_active_stages(self, *, error_code: str) -> None:
        for stage in list(self._started):
            self.finish(
                stage,
                outcome=TraceOutcome.ERROR,
                event_name="stage_failed",
                attributes={"error_code": error_code},
            )


def _event_id(
    *,
    trace_id: str,
    attempt: int,
    sequence: int,
    stage: str,
    event_name: str,
) -> str:
    material = f"{trace_id}|{attempt}|{sequence}|{stage}|{event_name}".encode()
    return f"evt_{hashlib.sha256(material).hexdigest()[:32]}"


def persist_trace_events(
    session: Session,
    events: Sequence[ProcessingTraceEvent],
) -> None:
    for event in events:
        if session.get(ProcessingTraceEventRow, event.event_id) is not None:
            continue
        session.add(
            ProcessingTraceEventRow(
                event_id=event.event_id,
                trace_id=event.trace_id,
                job_id=event.job_id,
                recording_id=event.recording_id,
                family_id=event.family_id,
                attempt=event.attempt,
                sequence=event.sequence,
                stage=event.stage,
                event_name=event.event_name,
                outcome=event.outcome.value,
                duration_ms=event.duration_ms,
                attributes=event.attributes,
                created_at=event.created_at,
            )
        )


class TraceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_job_trace(self, *, job_id: str) -> JobTraceView | None:
        with self.database.session_factory() as session:
            rows = list(
                session.scalars(
                    select(ProcessingTraceEventRow)
                    .where(ProcessingTraceEventRow.job_id == job_id)
                    .order_by(
                        ProcessingTraceEventRow.attempt,
                        ProcessingTraceEventRow.sequence,
                    )
                )
            )
        if not rows:
            return None
        events = [_row_to_event(row) for row in rows]
        stage_durations: dict[str, int] = {}
        for event in events:
            if event.duration_ms is not None:
                stage_durations[event.stage] = (
                    stage_durations.get(event.stage, 0) + event.duration_ms
                )
        return JobTraceView(
            trace_id=events[0].trace_id,
            job_id=events[0].job_id,
            recording_id=events[0].recording_id,
            family_id=events[0].family_id,
            attempts=sorted({event.attempt for event in events}),
            total_duration_ms=sum(stage_durations.values()),
            stage_durations_ms=stage_durations,
            events=events,
        )


def _row_to_event(row: ProcessingTraceEventRow) -> ProcessingTraceEvent:
    return ProcessingTraceEvent(
        event_id=row.event_id,
        trace_id=row.trace_id,
        job_id=row.job_id,
        recording_id=row.recording_id,
        family_id=row.family_id,
        attempt=row.attempt,
        sequence=row.sequence,
        stage=row.stage,
        event_name=row.event_name,
        outcome=TraceOutcome(row.outcome),
        duration_ms=row.duration_ms,
        attributes=row.attributes,
        created_at=row.created_at,
    )
