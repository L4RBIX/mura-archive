from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from mura.config import CoreSettings
from mura.jobs import WAITING_FOR_ASR_STAGE, JobStatus
from mura.leases import (
    WORKER_ID_PREFIX,
    LeaseHeartbeat,
    LeaseOwnershipLost,
    new_worker_id,
)
from mura.storage.database import Database, ProcessingJobRow, RecordingRepository, RecordingRow

OWNER_A = "worker_" + "a" * 32
OWNER_B = "worker_" + "b" * 32
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


@pytest.fixture
def repository() -> RecordingRepository:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    return RecordingRepository(database)


def _seed(repository: RecordingRepository, job_id: str = "job_1") -> None:
    with repository.database.session_factory.begin() as session:
        session.add(
            RecordingRow(
                recording_id=f"rec_{job_id}",
                family_id="family_a",
                speaker_id="narrator_rec",
                speaker_name="Айсұлу",
                original_filename="a.wav",
                content_type="audio/wav",
                audio_path="/tmp/a.wav",
            )
        )
        # PostgreSQL enforces the recordings FK, so the parent must land first.
        session.flush()
        session.add(
            ProcessingJobRow(
                job_id=job_id,
                recording_id=f"rec_{job_id}",
                status=JobStatus.QUEUED.value,
                stage="queued",
                next_attempt_at=NOW - timedelta(seconds=1),
            )
        )


def _aware(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on round-trip; PostgreSQL keeps it. Normalise for tests."""

    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _row(repository: RecordingRepository, job_id: str = "job_1") -> ProcessingJobRow:
    with repository.database.session_factory() as session:
        row = session.get(ProcessingJobRow, job_id)
        assert row is not None
        return row


def _set(repository: RecordingRepository, job_id: str = "job_1", **values: object) -> None:
    with repository.database.session_factory.begin() as session:
        row = session.get(ProcessingJobRow, job_id)
        assert row is not None
        for key, value in values.items():
            setattr(row, key, value)


# ----------------------------------------------------------------------- claim


def test_due_queued_job_is_claimed_with_lease(repository: RecordingRepository) -> None:
    _seed(repository)

    job = repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=300, now=NOW)

    assert job is not None
    assert job.lease_owner == OWNER_A
    assert job.claimed_at == NOW
    assert job.lease_expires_at == NOW + timedelta(seconds=300)
    assert job.status == JobStatus.TRANSCRIBING.value
    assert job.attempts == 1


def test_future_next_attempt_is_not_claimed(repository: RecordingRepository) -> None:
    _seed(repository)
    _set(repository, next_attempt_at=NOW + timedelta(seconds=60))

    assert repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=300, now=NOW) is None


def test_unexpired_lease_cannot_be_stolen(repository: RecordingRepository) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=300, now=NOW)

    second = repository.claim_next_job(
        lease_owner=OWNER_B, lease_seconds=300, now=NOW + timedelta(seconds=120)
    )

    assert second is None


def test_each_claim_counts_exactly_one_attempt(repository: RecordingRepository) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=60, now=NOW)
    later = NOW + timedelta(seconds=120)

    repository.claim_next_job(lease_owner=OWNER_B, lease_seconds=60, now=later)

    assert _row(repository).attempts == 2


# -------------------------------------------------------------------- recovery


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.TRANSCRIBING,
        JobStatus.CLEANING,
        JobStatus.EXTRACTING,
        JobStatus.RESOLVING,
    ],
)
def test_expired_lease_is_recoverable_from_any_processing_state(
    repository: RecordingRepository,
    status: JobStatus,
) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=60, now=NOW)
    _set(repository, status=status.value, stage=status.value)

    recovered = repository.claim_next_job(
        lease_owner=OWNER_B, lease_seconds=60, now=NOW + timedelta(seconds=120)
    )

    assert recovered is not None
    assert recovered.lease_owner == OWNER_B


@pytest.mark.parametrize("status", [JobStatus.COMPLETED, JobStatus.FAILED])
def test_terminal_jobs_are_never_reclaimed(
    repository: RecordingRepository,
    status: JobStatus,
) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=60, now=NOW)
    _set(repository, status=status.value, lease_expires_at=NOW - timedelta(seconds=1))

    assert (
        repository.claim_next_job(
            lease_owner=OWNER_B, lease_seconds=60, now=NOW + timedelta(seconds=600)
        )
        is None
    )


# --------------------------------------------------------------------- renewal


def test_owner_renews_and_records_heartbeat(repository: RecordingRepository) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=60, now=NOW)
    later = NOW + timedelta(seconds=30)

    assert repository.renew_lease("job_1", lease_owner=OWNER_A, lease_seconds=60, now=later) is True
    row = _row(repository)
    assert _aware(row.lease_expires_at) == later + timedelta(seconds=60)
    assert _aware(row.last_heartbeat_at) == later


def test_wrong_owner_cannot_renew(repository: RecordingRepository) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=60, now=NOW)

    assert repository.renew_lease("job_1", lease_owner=OWNER_B, lease_seconds=60) is False


def test_terminal_job_cannot_be_renewed(repository: RecordingRepository) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=60, now=NOW)
    _set(repository, status=JobStatus.COMPLETED.value)

    assert repository.renew_lease("job_1", lease_owner=OWNER_A, lease_seconds=60) is False


# --------------------------------------------------------------- stale worker


def test_stale_worker_cannot_defer_or_fail_or_move_stage(
    repository: RecordingRepository,
) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=60, now=NOW)
    # B legitimately reclaims after A's lease expires.
    repository.claim_next_job(
        lease_owner=OWNER_B, lease_seconds=60, now=NOW + timedelta(seconds=120)
    )

    with pytest.raises(LeaseOwnershipLost):
        repository.defer_job(
            "job_1",
            error_code="asr_worker_unavailable",
            error_detail="unavailable",
            retry_after_seconds=15,
            lease_owner=OWNER_A,
        )
    with pytest.raises(LeaseOwnershipLost):
        repository.fail_job(
            "job_1", error_code="pipeline_failed", error_detail="x", lease_owner=OWNER_A
        )
    with pytest.raises(LeaseOwnershipLost):
        repository.update_job_stage(
            "job_1", JobStatus.TRANSCRIBING, "asr_transcription", lease_owner=OWNER_A
        )
    # B's ownership and state survived every stale attempt.
    assert _row(repository).lease_owner == OWNER_B


# ----------------------------------------------------------------------- defer


def test_defer_releases_the_lease_and_preserves_backoff(
    repository: RecordingRepository,
) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=300, now=NOW)
    attempts_after_claim = _row(repository).attempts

    repository.defer_job(
        "job_1",
        error_code="asr_worker_unavailable",
        error_detail="no ready ASR worker is registered",
        retry_after_seconds=15,
        lease_owner=OWNER_A,
    )

    row = _row(repository)
    assert row.status == JobStatus.QUEUED.value
    assert row.stage == WAITING_FOR_ASR_STAGE
    assert row.lease_owner is None
    assert row.lease_expires_at is None
    assert _aware(row.next_attempt_at) > NOW
    # attempts counts claims; deferring must not inflate it a second time.
    assert row.attempts == attempts_after_claim


def test_deferred_job_cannot_be_renewed(repository: RecordingRepository) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=300, now=NOW)
    repository.defer_job(
        "job_1",
        error_code="asr_worker_unavailable",
        error_detail="x",
        retry_after_seconds=15,
        lease_owner=OWNER_A,
    )

    assert repository.renew_lease("job_1", lease_owner=OWNER_A, lease_seconds=300) is False


def test_deferred_job_is_only_claimable_once_due(repository: RecordingRepository) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=300, now=NOW)
    repository.defer_job(
        "job_1",
        error_code="asr_worker_unavailable",
        error_detail="x",
        retry_after_seconds=60,
        lease_owner=OWNER_A,
    )

    # defer_job stamps next_attempt_at from the real clock, so measure from it.
    due_at = _aware(_row(repository).next_attempt_at)
    assert due_at is not None

    assert (
        repository.claim_next_job(
            lease_owner=OWNER_B, lease_seconds=300, now=due_at - timedelta(seconds=1)
        )
        is None
    )
    assert (
        repository.claim_next_job(
            lease_owner=OWNER_B, lease_seconds=300, now=due_at + timedelta(seconds=1)
        )
        is not None
    )


# ------------------------------------------------------------------------ fail


def test_failure_is_terminal_and_clears_the_lease(repository: RecordingRepository) -> None:
    _seed(repository)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=300, now=NOW)

    repository.fail_job(
        "job_1", error_code="pipeline_failed", error_detail="x", lease_owner=OWNER_A
    )

    row = _row(repository)
    assert row.status == JobStatus.FAILED.value
    assert row.lease_owner is None
    assert (
        repository.claim_next_job(
            lease_owner=OWNER_B, lease_seconds=300, now=NOW + timedelta(days=1)
        )
        is None
    )


# ------------------------------------------------------------------ worker id


def test_worker_id_is_random_and_privacy_safe() -> None:
    first, second = new_worker_id(), new_worker_id()

    assert first != second
    assert first.startswith(WORKER_ID_PREFIX)
    import getpass
    import socket

    assert getpass.getuser().lower() not in first.lower()
    assert socket.gethostname().lower() not in first.lower()


# ------------------------------------------------------------------ heartbeat


def test_heartbeat_renews_while_work_blocks() -> None:
    ticks = threading.Semaphore(0)
    released = threading.Event()

    def renew() -> bool:
        ticks.release()
        return True

    heartbeat = LeaseHeartbeat(job_id="job_1", renew=renew, interval_seconds=0.01)
    with heartbeat:
        # Simulate a blocking provider call: the main thread never yields to a
        # poll loop, yet the lease must still be renewed.
        assert ticks.acquire(timeout=5)
        assert ticks.acquire(timeout=5)
        released.set()

    assert released.is_set()
    assert heartbeat.ownership_lost is False


def test_heartbeat_stops_after_the_context_exits() -> None:
    calls: list[int] = []
    heartbeat = LeaseHeartbeat(
        job_id="job_1", renew=lambda: (calls.append(1), True)[1], interval_seconds=0.01
    )

    with heartbeat:
        while not calls:
            pass
    observed = len(calls)

    assert heartbeat._thread is None
    assert len(calls) == observed


def test_heartbeat_detects_explicit_ownership_loss() -> None:
    lost = threading.Event()
    heartbeat = LeaseHeartbeat(
        job_id="job_1",
        renew=lambda: False,
        interval_seconds=0.01,
        on_ownership_lost=lost.set,
    )

    with heartbeat:
        assert lost.wait(timeout=5)

    assert heartbeat.ownership_lost is True


def test_transient_renewal_errors_do_not_abandon_ownership() -> None:
    attempts: list[int] = []

    def flaky() -> bool:
        attempts.append(1)
        if len(attempts) < 3:
            raise TimeoutError("database briefly unreachable")
        return True

    heartbeat = LeaseHeartbeat(job_id="job_1", renew=flaky, interval_seconds=0.01)
    with heartbeat:
        while len(attempts) < 3:
            pass

    # A blip is not proof that ownership moved; only an explicit rejection is.
    assert heartbeat.ownership_lost is False


# --------------------------------------------------------------------- config


def _settings(**overrides: object) -> CoreSettings:
    payload: dict[str, object] = {
        "DEEPSEEK_API_KEY": "sk-" + "d" * 40,
        "CORE_API_KEY": "c" * 40,
        "WORKER_REGISTRATION_TOKEN": "r" * 40,
        "KAGGLE_ASR_API_KEY": "a" * 40,
        "OPERATIONS_API_KEY": "o" * 40,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    }
    payload.update(overrides)
    return CoreSettings.model_validate(payload)


def test_default_lease_settings_are_valid_and_sized_for_real_providers() -> None:
    settings = _settings()

    assert settings.job_lease_seconds == 300
    assert settings.job_heartbeat_seconds == 60
    # Room for several missed heartbeats before another worker may recover.
    assert settings.job_lease_seconds >= 3 * settings.job_heartbeat_seconds


@pytest.mark.parametrize(
    ("lease", "heartbeat"),
    [(60, 60), (60, 90), (60, 30)],
)
def test_heartbeat_must_fit_several_times_inside_the_lease(lease: int, heartbeat: int) -> None:
    with pytest.raises(ValidationError):
        _settings(JOB_LEASE_SECONDS=lease, JOB_HEARTBEAT_SECONDS=heartbeat)


@pytest.mark.parametrize(("lease", "heartbeat"), [(0, 1), (300, 0), (-5, 1)])
def test_non_positive_lease_settings_are_rejected(lease: int, heartbeat: int) -> None:
    with pytest.raises(ValidationError):
        _settings(JOB_LEASE_SECONDS=lease, JOB_HEARTBEAT_SECONDS=heartbeat)


# ------------------------------------------------------------------ migration


def test_migration_0008_follows_0007_and_adds_lease_columns() -> None:
    from pathlib import Path

    source = Path("migrations/versions/20260719_0008_job_leases.py").read_text(encoding="utf-8")
    module: dict[str, object] = {}
    exec(compile(source, "0008", "exec"), module)

    assert module["revision"] == "20260719_0008"
    assert module["down_revision"] == "20260719_0007"
    for column in ("lease_owner", "claimed_at", "lease_expires_at", "last_heartbeat_at"):
        assert column in source
    assert source.count("op.add_column") == 4
    assert source.count("op.drop_column") == 4
    assert source.count("op.create_index") == 2
    assert source.count("op.drop_index") == 2
