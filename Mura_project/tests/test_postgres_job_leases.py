"""Lease semantics that only a real PostgreSQL server can prove.

SQLite cannot demonstrate FOR UPDATE SKIP LOCKED, concurrent claim arbitration
or row-level lock behaviour, so these tests are the authoritative validation for
PR-02B-i and are the reason the milestone is not production-valid until they run.

Enable with a disposable database only::

    $env:TEST_POSTGRES_URL = 'postgresql+psycopg://user:pw@127.0.0.1:5432/mura_leases_test'
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from mura.jobs import JobStatus
from mura.leases import LeaseOwnershipLost
from mura.storage.database import (
    Database,
    ProcessingJobRow,
    RecordingRepository,
    RecordingRow,
)

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="TEST_POSTGRES_URL is required for the PostgreSQL lease concurrency tests",
    ),
    # Never point these at a real database: every test truncates the job tables.
    pytest.mark.skipif(
        bool(POSTGRES_URL) and "test" not in (POSTGRES_URL or "").rsplit("/", 1)[-1].lower(),
        reason="TEST_POSTGRES_URL database name must contain 'test' to be treated as disposable",
    ),
]

OWNER_A = "worker_" + "a" * 32
OWNER_B = "worker_" + "b" * 32


def _purge(database: Database) -> None:
    with database.session_factory.begin() as session:
        session.query(ProcessingJobRow).delete()
        session.query(RecordingRow).delete()


@pytest.fixture
def repository() -> Iterator[RecordingRepository]:
    assert POSTGRES_URL is not None
    database = Database(POSTGRES_URL)
    database.create_schema()
    _purge(database)
    yield RecordingRepository(database)
    # Leave the shared disposable database empty: claim_next_job takes the
    # oldest eligible job, so rows left behind would be claimed by unrelated
    # suites running later against the same database.
    _purge(database)


def _seed(repository: RecordingRepository, job_id: str, *, due_seconds: int = -1) -> None:
    now = datetime.now(UTC)
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
                next_attempt_at=now + timedelta(seconds=due_seconds),
            )
        )


def test_two_workers_racing_for_one_job_produce_exactly_one_claim(
    repository: RecordingRepository,
) -> None:
    _seed(repository, "job_race")
    results: list[object] = []
    barrier = threading.Barrier(2)

    def claim(owner: str) -> None:
        barrier.wait(timeout=10)
        results.append(repository.claim_next_job(lease_owner=owner, lease_seconds=300))

    threads = [
        threading.Thread(target=claim, args=(OWNER_A,)),
        threading.Thread(target=claim, args=(OWNER_B,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    claimed = [item for item in results if item is not None]
    assert len(claimed) == 1
    assert len(results) == 2


def test_skip_locked_lets_a_second_worker_take_a_different_job(
    repository: RecordingRepository,
) -> None:
    _seed(repository, "job_one")
    _seed(repository, "job_two")

    # Hold a row lock open in one transaction, then claim from another session.
    with repository.database.session_factory.begin() as session:
        locked = (
            session.query(ProcessingJobRow)
            .order_by(ProcessingJobRow.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
            .one()
        )
        other = repository.claim_next_job(lease_owner=OWNER_B, lease_seconds=300)

        assert other is not None
        assert other.job_id != locked.job_id


def test_unexpired_lease_is_not_reclaimable(repository: RecordingRepository) -> None:
    _seed(repository, "job_lease")
    first = repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=300)

    assert first is not None
    assert repository.claim_next_job(lease_owner=OWNER_B, lease_seconds=300) is None


def test_expired_lease_is_reclaimable(repository: RecordingRepository) -> None:
    _seed(repository, "job_expired")
    now = datetime.now(UTC)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=1, now=now - timedelta(hours=1))

    recovered = repository.claim_next_job(lease_owner=OWNER_B, lease_seconds=300, now=now)

    assert recovered is not None
    assert recovered.lease_owner == OWNER_B


def test_stale_owner_cannot_defer_or_fail(repository: RecordingRepository) -> None:
    _seed(repository, "job_stale")
    now = datetime.now(UTC)
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=1, now=now - timedelta(hours=1))
    repository.claim_next_job(lease_owner=OWNER_B, lease_seconds=300, now=now)

    with pytest.raises(LeaseOwnershipLost):
        repository.defer_job(
            "job_stale",
            error_code="asr_worker_unavailable",
            error_detail="x",
            retry_after_seconds=15,
            lease_owner=OWNER_A,
        )
    with pytest.raises(LeaseOwnershipLost):
        repository.fail_job(
            "job_stale", error_code="pipeline_failed", error_detail="x", lease_owner=OWNER_A
        )

    with repository.database.session_factory() as session:
        row = session.get(ProcessingJobRow, "job_stale")
        assert row is not None
        assert row.lease_owner == OWNER_B


def test_renewal_is_owner_scoped_on_real_postgres(repository: RecordingRepository) -> None:
    _seed(repository, "job_renew")
    repository.claim_next_job(lease_owner=OWNER_A, lease_seconds=300)

    assert repository.renew_lease("job_renew", lease_owner=OWNER_A, lease_seconds=300) is True
    assert repository.renew_lease("job_renew", lease_owner=OWNER_B, lease_seconds=300) is False
