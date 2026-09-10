"""Standalone recording worker.

The API process used to run the worker on a background thread, which coupled two
very different lifecycles: a request-serving process that should start instantly
and scale on demand, and a job runner that holds a lease for many minutes. This
entrypoint separates them. The API now only submits and reads jobs; this process
claims and executes them.

Safety rests on the lease from PR-02B-i, not on shutdown bookkeeping. If this
process dies mid-recording -- SIGTERM, power loss, anything -- the lease simply
expires and another worker reclaims the job. Nothing here ever marks in-flight
work completed or failed just because the process is stopping.
"""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType

from mura.asr.factory import build_asr_client
from mura.config import CoreSettings
from mura.deepseek import DeepSeekClient, DeepSeekPipelineService
from mura.orchestration import LocalAudioStorage, RecordingJobWorker
from mura.pipeline import MuraPipeline
from mura.storage.database import Database, DatabaseRuntimeSettings, RecordingRepository

logger = logging.getLogger("mura.worker")


def build_worker(settings: CoreSettings) -> RecordingJobWorker:
    """Construct the worker and everything it owns, once per process."""

    database = Database(
        settings.database_url,
        runtime=DatabaseRuntimeSettings(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle_seconds=settings.db_pool_recycle_seconds,
            connect_timeout_seconds=settings.db_connect_timeout_seconds,
            statement_timeout_seconds=settings.db_statement_timeout_seconds,
        ),
    )
    # Schema management belongs to Alembic; the worker never creates tables.
    pipeline = MuraPipeline(
        DeepSeekPipelineService(
            DeepSeekClient(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                primary_model=settings.deepseek_model,
                fallback_model=settings.deepseek_fallback_model,
            ),
            focused_extraction=True,
        )
    )
    return RecordingJobWorker(
        repository=RecordingRepository(database),
        pipeline=pipeline,
        storage=LocalAudioStorage(
            settings.audio_storage_dir,
            max_upload_bytes=settings.core_max_upload_mb * 1024 * 1024,
        ),
        asr_client=build_asr_client(settings),
        poll_interval_seconds=settings.job_poll_interval_seconds,
        asr_retry_seconds=settings.asr_retry_seconds,
        lease_seconds=settings.job_lease_seconds,
        heartbeat_seconds=settings.job_heartbeat_seconds,
    )


def install_signal_handlers(worker: RecordingJobWorker) -> None:
    """Stop claiming new work on termination. Works on Windows and POSIX."""

    def handle(signum: int, _frame: FrameType | None) -> None:
        logger.info("worker received signal %s; finishing current work", signum)
        # Only stops the claim loop. In-flight processing is left alone and its
        # lease expiry, not this handler, is what makes the job recoverable.
        worker.request_stop()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        received = getattr(signal, name, None)
        if received is not None:
            try:
                signal.signal(received, handle)
            except (OSError, ValueError):
                # Not all signals are settable on every platform or thread.
                logger.debug("signal %s unavailable in this environment", name)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        settings = CoreSettings()  # type: ignore[call-arg]
    except Exception:
        # Never echo the validation error: it can quote supplied secrets.
        logger.error("worker is not configured; refusing to start")
        return 2

    worker = build_worker(settings)
    install_signal_handlers(worker)
    logger.info(
        "worker starting worker_id=%s lease=%ss heartbeat=%ss",
        worker.worker_id,
        settings.job_lease_seconds,
        settings.job_heartbeat_seconds,
    )
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        logger.info("worker interrupted")
    finally:
        worker.stop()
    logger.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
