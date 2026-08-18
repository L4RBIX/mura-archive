"""Durable job lease ownership.

A lease answers one question: which worker process is currently allowed to
mutate this job. It is operational identity only -- never a user, never a
family, and never exposed through the public API.

The mechanism exists because a worker can die mid-recording. Without a lease the
job stays in `transcribing` forever; with one, the lease simply expires and
another worker reclaims it. The cost is that a *slow* worker must keep proving
it is alive, which is what the heartbeat below does.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from types import TracebackType

logger = logging.getLogger(__name__)

#: Prefix keeps lease owners visually distinct from job/recording identifiers.
WORKER_ID_PREFIX = "worker_"


class LeaseOwnershipLost(RuntimeError):
    """This process no longer owns the job and must stop mutating it.

    Raised instead of letting a stale worker overwrite the state or archive
    result of whichever worker legitimately reclaimed the job.
    """

    def __init__(self, job_id: str) -> None:
        super().__init__(f"lease ownership lost for job {job_id}")
        self.job_id = job_id


def new_worker_id() -> str:
    """Random, privacy-safe operational identity.

    Deliberately carries no hostname, username or PID: worker ids reach traces
    and operator tooling, and none of that context is needed to tell two
    concurrent workers apart.
    """

    return f"{WORKER_ID_PREFIX}{uuid.uuid4().hex}"


class LeaseHeartbeat:
    """Renews one job's lease from a side thread while processing blocks.

    The main flow spends most of its time inside `RemoteASRClient.transcribe()`
    or DeepSeek calls, which can legitimately run for many minutes and never
    yield. Renewing between stages would therefore be far too coarse, so a
    dedicated thread ticks on its own timer for the life of a single claimed job.

    Each tick calls `renew`, which must open its own short-lived session: a
    SQLAlchemy Session belongs to one thread and must not be shared with the
    processing flow.
    """

    def __init__(
        self,
        *,
        job_id: str,
        renew: Callable[[], bool],
        interval_seconds: float,
        on_ownership_lost: Callable[[], None] | None = None,
    ) -> None:
        self._job_id = job_id
        self._renew = renew
        self._interval = interval_seconds
        self._on_ownership_lost = on_ownership_lost
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ownership_lost = threading.Event()

    @property
    def ownership_lost(self) -> bool:
        """True once a renewal was explicitly rejected by the database."""

        return self._ownership_lost.is_set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                renewed = self._renew()
            except Exception:
                # A transient database problem is not proof that ownership
                # moved, so keep ticking inside the remaining lease window. The
                # authoritative check happens once more before any terminal
                # write, so a genuinely lost lease can never commit.
                logger.warning("lease renewal failed transiently", exc_info=False)
                continue
            if not renewed:
                # An explicit rejection is authoritative: another worker owns it.
                self._ownership_lost.set()
                if self._on_ownership_lost is not None:
                    self._on_ownership_lost()
                return

    def start(self) -> LeaseHeartbeat:
        if self._thread is not None:
            return self
        self._thread = threading.Thread(
            target=self._run,
            name=f"mura-lease-{self._job_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout_seconds)
            self._thread = None

    def __enter__(self) -> LeaseHeartbeat:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()
