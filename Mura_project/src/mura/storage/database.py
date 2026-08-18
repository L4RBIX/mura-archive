from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    and_,
    create_engine,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult

from mura.domain.models import PipelineResult
from mura.jobs import WAITING_FOR_ASR_STAGE, JobStatus
from mura.leases import LeaseOwnershipLost

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")

#: A terminal job is never reclaimed and never renewable.
TERMINAL_JOB_STATUSES = (JobStatus.COMPLETED.value, JobStatus.FAILED.value)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _release_lease(job: ProcessingJobRow) -> None:
    """Drop ownership so the row is either terminal or cleanly reclaimable."""

    job.lease_owner = None
    job.claimed_at = None
    job.lease_expires_at = None


class Base(DeclarativeBase):
    pass


class RecordingRow(Base):
    __tablename__ = "recordings"

    recording_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    speaker_id: Mapped[str] = mapped_column(String(128), index=True)
    speaker_name: Mapped[str] = mapped_column(String(256))
    original_filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Legacy locator. Recordings created before storage keys existed have this
    #: and a NULL storage_key; canonical recordings always populate storage_key.
    audio_path: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_backend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    audio_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Nullable only so historical rows migrate cleanly. Recordings created
    #: through the canonical API always persist explicit values; NULL is read as
    #: AudioLanguage.AUTO / OutputLanguage.SAME_AS_TRANSCRIPT.
    audio_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    output_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessingJobRow(Base):
    __tablename__ = "processing_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recording_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("recordings.recording_id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=JobStatus.QUEUED.value,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Operational lease. NULL means no worker currently owns the job, which is
    #: also how every historical row reads after the migration.
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class PipelineResultRow(Base):
    __tablename__ = "pipeline_results"

    recording_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("recordings.recording_id", ondelete="CASCADE"),
        primary_key=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class WorkerRegistrationRow(Base):
    __tablename__ = "worker_registrations"

    worker_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="ready")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@dataclass(frozen=True)
class DatabaseRuntimeSettings:
    """Conservative connection-pool defaults for a single managed PostgreSQL deployment.

    Defaults assume several small API/worker processes sharing one managed instance:
    5 pooled connections plus 5 overflow per process, recycled every 30 minutes so
    proxy-side idle timeouts never hand back a dead socket. Timeouts are applied
    per-connection for PostgreSQL only and are ignored by the SQLite test path.
    """

    pool_size: int = 5
    max_overflow: int = 5
    pool_recycle_seconds: int = 1800
    connect_timeout_seconds: int = 10
    statement_timeout_seconds: int = 30


def postgres_connect_args(runtime: DatabaseRuntimeSettings) -> dict[str, Any]:
    return {
        "connect_timeout": runtime.connect_timeout_seconds,
        "options": f"-c statement_timeout={runtime.statement_timeout_seconds * 1000}",
    }


class Database:
    def __init__(
        self,
        database_url: str,
        runtime: DatabaseRuntimeSettings | None = None,
    ) -> None:
        resolved = runtime or DatabaseRuntimeSettings()
        connect_args: dict[str, Any] = {}
        engine_options: dict[str, Any] = {"pool_pre_ping": True, "future": True}

        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            if ":memory:" in database_url:
                engine_options["poolclass"] = StaticPool
        else:
            engine_options["pool_size"] = resolved.pool_size
            engine_options["max_overflow"] = resolved.max_overflow
            engine_options["pool_recycle"] = resolved.pool_recycle_seconds
            if database_url.startswith(("postgresql", "postgres")):
                connect_args.update(postgres_connect_args(resolved))

        self.engine = create_engine(database_url, connect_args=connect_args, **engine_options)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)


class RecordingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_recording_and_job(
        self,
        *,
        recording_id: str,
        job_id: str,
        family_id: str,
        speaker_id: str,
        speaker_name: str,
        original_filename: str,
        content_type: str | None,
        audio_path: Path | str,
        audio_language: str | None = None,
        output_language: str | None = None,
        storage_key: str | None = None,
        storage_backend: str | None = None,
        audio_sha256: str | None = None,
        audio_size_bytes: int | None = None,
        audio_mime_type: str | None = None,
    ) -> None:
        with self.database.session_factory.begin() as session:
            session.add(
                RecordingRow(
                    recording_id=recording_id,
                    family_id=family_id,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                    original_filename=original_filename,
                    content_type=content_type,
                    audio_path=str(audio_path),
                    storage_key=storage_key,
                    storage_backend=storage_backend,
                    audio_sha256=audio_sha256,
                    audio_size_bytes=audio_size_bytes,
                    audio_mime_type=audio_mime_type,
                    audio_language=audio_language,
                    output_language=output_language,
                )
            )
            session.flush()
            session.add(
                ProcessingJobRow(
                    job_id=job_id,
                    recording_id=recording_id,
                    status=JobStatus.QUEUED.value,
                    stage="queued",
                )
            )

    def get_recording(self, recording_id: str) -> RecordingRow | None:
        with self.database.session_factory() as session:
            return session.get(RecordingRow, recording_id)

    # ---------------------------------------------------------------- family scope
    #
    # Every canonical application lookup goes through one of these. The family
    # predicate is part of the query, so a foreign resource is never loaded and
    # then rejected -- it simply does not exist for that family. Routes turn the
    # None into a 404, which is indistinguishable from "no such id" and so
    # cannot confirm another family's object.

    def get_family_recording(
        self,
        *,
        family_id: str,
        recording_id: str,
    ) -> RecordingRow | None:
        with self.database.session_factory() as session:
            statement = select(RecordingRow).where(
                RecordingRow.recording_id == recording_id,
                RecordingRow.family_id == family_id,
            )
            return session.scalar(statement)

    def get_family_job(self, *, family_id: str, job_id: str) -> ProcessingJobRow | None:
        with self.database.session_factory() as session:
            statement = (
                select(ProcessingJobRow)
                .join(RecordingRow, RecordingRow.recording_id == ProcessingJobRow.recording_id)
                .where(
                    ProcessingJobRow.job_id == job_id,
                    RecordingRow.family_id == family_id,
                )
            )
            return session.scalar(statement)

    def get_family_job_for_recording(
        self,
        *,
        family_id: str,
        recording_id: str,
    ) -> ProcessingJobRow | None:
        with self.database.session_factory() as session:
            statement = (
                select(ProcessingJobRow)
                .join(RecordingRow, RecordingRow.recording_id == ProcessingJobRow.recording_id)
                .where(
                    ProcessingJobRow.recording_id == recording_id,
                    RecordingRow.family_id == family_id,
                )
            )
            return session.scalar(statement)

    def get_family_pipeline_result(
        self,
        *,
        family_id: str,
        recording_id: str,
    ) -> PipelineResult | None:
        with self.database.session_factory() as session:
            statement = (
                select(PipelineResultRow)
                .join(RecordingRow, RecordingRow.recording_id == PipelineResultRow.recording_id)
                .where(
                    PipelineResultRow.recording_id == recording_id,
                    RecordingRow.family_id == family_id,
                )
            )
            row = session.scalar(statement)
            return None if row is None else PipelineResult.model_validate(row.payload)

    def family_person_exists(self, *, family_id: str, person_id: str) -> bool:
        """Canonical identity check: existence *and* family ownership together."""

        from mura.storage.archive import ArchivePersonRow

        with self.database.session_factory() as session:
            statement = select(ArchivePersonRow.person_id).where(
                ArchivePersonRow.person_id == person_id,
                ArchivePersonRow.family_id == family_id,
            )
            return session.scalar(statement) is not None

    def get_job(self, job_id: str) -> ProcessingJobRow | None:
        with self.database.session_factory() as session:
            return session.get(ProcessingJobRow, job_id)

    def get_job_for_recording(self, recording_id: str) -> ProcessingJobRow | None:
        with self.database.session_factory() as session:
            statement = select(ProcessingJobRow).where(
                ProcessingJobRow.recording_id == recording_id
            )
            return session.scalar(statement)

    def get_pipeline_result(self, recording_id: str) -> PipelineResult | None:
        with self.database.session_factory() as session:
            row = session.get(PipelineResultRow, recording_id)
            if row is None:
                return None
            return PipelineResult.model_validate(row.payload)

    def claim_next_job(
        self,
        *,
        lease_owner: str,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> ProcessingJobRow | None:
        """Atomically take ownership of one eligible job.

        Two categories are eligible, and both are resolved inside the same
        `FOR UPDATE SKIP LOCKED` transaction as the ownership write, so the row
        is never selected, released and only later stamped:

        1. a queued job whose ``next_attempt_at`` is due;
        2. a non-terminal job whose lease has expired -- the crash-recovery
           case, where the previous worker died mid-processing.

        Terminal jobs are excluded outright, and an unexpired lease is never
        stolen. Each successful claim is one processing attempt.
        """

        moment = now or utcnow()
        with self.database.session_factory.begin() as session:
            due_queued = and_(
                ProcessingJobRow.status == JobStatus.QUEUED.value,
                ProcessingJobRow.next_attempt_at <= moment,
                or_(
                    ProcessingJobRow.lease_expires_at.is_(None),
                    ProcessingJobRow.lease_expires_at <= moment,
                ),
            )
            expired_lease = and_(
                ProcessingJobRow.status.notin_(TERMINAL_JOB_STATUSES),
                ProcessingJobRow.lease_expires_at.is_not(None),
                ProcessingJobRow.lease_expires_at <= moment,
            )
            statement = (
                select(ProcessingJobRow)
                .where(or_(due_queued, expired_lease))
                .order_by(ProcessingJobRow.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            job = session.scalar(statement)
            if job is None:
                return None
            job.lease_owner = lease_owner
            job.claimed_at = moment
            job.lease_expires_at = moment + timedelta(seconds=lease_seconds)
            job.last_heartbeat_at = moment
            job.attempts += 1
            job.status = JobStatus.TRANSCRIBING.value
            job.stage = "asr_transcription"
            job.started_at = job.started_at or moment
            job.updated_at = moment
            job.error_code = None
            job.error_detail = None
            session.flush()
            session.expunge(job)
            return job

    def renew_lease(
        self,
        job_id: str,
        *,
        lease_owner: str,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> bool:
        """Extend the lease, but only for the current owner of a live job.

        Returns False rather than raising so the heartbeat thread can treat an
        explicit rejection as authoritative ownership loss. A terminal job is
        never renewable, which is what stops a heartbeat outliving a deferred or
        failed attempt.
        """

        moment = now or utcnow()
        with self.database.session_factory.begin() as session:
            result = session.execute(
                update(ProcessingJobRow)
                .where(
                    ProcessingJobRow.job_id == job_id,
                    ProcessingJobRow.lease_owner == lease_owner,
                    ProcessingJobRow.status.notin_(TERMINAL_JOB_STATUSES),
                )
                .values(
                    lease_expires_at=moment + timedelta(seconds=lease_seconds),
                    last_heartbeat_at=moment,
                )
            )
            # CursorResult exposes rowcount; the base Result protocol does not.
            return bool(cast("CursorResult[Any]", result).rowcount)

    def _owned_job(
        self,
        session: Session,
        job_id: str,
        lease_owner: str | None,
    ) -> ProcessingJobRow:
        job = session.get(ProcessingJobRow, job_id)
        if job is None:
            raise LookupError(f"unknown job: {job_id}")
        # None means an unowned administrative write; a worker always passes its
        # id and must still hold the lease.
        if lease_owner is not None and job.lease_owner != lease_owner:
            raise LeaseOwnershipLost(job_id)
        return job

    def update_job_stage(
        self,
        job_id: str,
        status: JobStatus,
        stage: str,
        *,
        lease_owner: str | None = None,
    ) -> None:
        with self.database.session_factory.begin() as session:
            job = self._owned_job(session, job_id, lease_owner)
            job.status = status.value
            job.stage = stage
            job.updated_at = utcnow()

    def defer_job(
        self,
        job_id: str,
        *,
        error_code: str,
        error_detail: str,
        retry_after_seconds: float,
        lease_owner: str | None = None,
    ) -> None:
        """Return the job to the queue for Core's own later retry.

        Ownership is released so the job becomes reclaimable once due, and
        `attempts` is deliberately not touched: the count means claims, and the
        next claim will increment it.
        """

        now = utcnow()
        with self.database.session_factory.begin() as session:
            job = self._owned_job(session, job_id, lease_owner)
            job.status = JobStatus.QUEUED.value
            job.stage = WAITING_FOR_ASR_STAGE
            job.next_attempt_at = now + timedelta(seconds=retry_after_seconds)
            job.error_code = error_code
            job.error_detail = error_detail
            job.updated_at = now
            _release_lease(job)

    def fail_job(
        self,
        job_id: str,
        *,
        error_code: str,
        error_detail: str,
        lease_owner: str | None = None,
    ) -> None:
        now = utcnow()
        with self.database.session_factory.begin() as session:
            job = self._owned_job(session, job_id, lease_owner)
            job.status = JobStatus.FAILED.value
            job.stage = "failed"
            job.error_code = error_code
            job.error_detail = error_detail
            job.completed_at = now
            job.updated_at = now
            _release_lease(job)

    def complete_job(self, job_id: str, result: PipelineResult) -> None:
        now = utcnow()
        payload = result.model_dump(mode="json")
        with self.database.session_factory.begin() as session:
            job = session.get(ProcessingJobRow, job_id)
            if job is None:
                raise LookupError(f"unknown job: {job_id}")
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
            job.status = JobStatus.COMPLETED.value
            job.stage = "completed"
            job.error_code = None
            job.error_detail = None
            job.completed_at = now
            job.updated_at = now

    def register_worker(self, *, url: str, status: str) -> WorkerRegistrationRow:
        now = utcnow()
        with self.database.session_factory.begin() as session:
            row = session.get(WorkerRegistrationRow, "kaggle-asr")
            if row is None:
                row = WorkerRegistrationRow(
                    worker_name="kaggle-asr",
                    url=url.rstrip("/"),
                    status=status,
                    registered_at=now,
                )
                session.add(row)
            else:
                row.url = url.rstrip("/")
                row.status = status
                row.registered_at = now
            session.flush()
            session.expunge(row)
            return row

    def current_worker(self) -> WorkerRegistrationRow | None:
        with self.database.session_factory() as session:
            return session.get(WorkerRegistrationRow, "kaggle-asr")
