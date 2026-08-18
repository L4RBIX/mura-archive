from __future__ import annotations

import logging
import threading
import time

from mura.asr import ASRClientError, RemoteASRClient
from mura.domain.models import (
    AudioLanguage,
    OutputLanguage,
    PipelineRequest,
    PipelineResult,
)
from mura.jobs import JobStatus
from mura.leases import LeaseHeartbeat, LeaseOwnershipLost, new_worker_id
from mura.observability import ProcessingTrace, TraceOutcome
from mura.pipeline import MuraPipeline
from mura.storage.archive import ArchiveRepository
from mura.storage.audio import AudioStorage
from mura.storage.completion import (
    defer_recording_job,
    fail_recording_job,
    finalize_recording_job,
)
from mura.storage.conflict_resolution import ConflictResolutionService
from mura.storage.database import ProcessingJobRow, RecordingRepository
from mura.storage.generic_claims import persist_generic_claims
from mura.storage.recording_audio import materialize_recording_audio

logger = logging.getLogger(__name__)


class RecordingJobWorker:
    def __init__(
        self,
        *,
        repository: RecordingRepository,
        pipeline: MuraPipeline,
        asr_client: RemoteASRClient,
        storage: AudioStorage | None = None,
        poll_interval_seconds: float = 1.0,
        asr_retry_seconds: float = 15.0,
        lease_seconds: float = 300.0,
        heartbeat_seconds: float = 60.0,
        worker_id: str | None = None,
    ) -> None:
        self.repository = repository
        self.archive_repository = ArchiveRepository(repository.database)
        self.conflict_resolution = ConflictResolutionService(repository.database)
        self.pipeline = pipeline
        self.asr_client = asr_client
        #: Optional so legacy recordings with only audio_path still process.
        self.storage = storage
        self.poll_interval_seconds = poll_interval_seconds
        self.asr_retry_seconds = asr_retry_seconds
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        #: Operational identity only. Never a user, never exposed publicly.
        self.worker_id = worker_id or new_worker_id()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="mura-recording-worker",
            daemon=True,
        )
        self._thread.start()

    def request_stop(self) -> None:
        """Stop claiming new work without disturbing the job in flight.

        Deliberately does not touch the current job: a shutdown must never mark
        in-progress work completed or failed. Lease expiry is the recovery
        mechanism if the process does not survive to finish it.
        """

        self._stop_event.set()

    def run_forever(self) -> None:
        """Claim and process until asked to stop. Used by the standalone worker."""

        self._run()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout_seconds)

    def process_once(self) -> bool:
        job = self.repository.claim_next_job(
            lease_owner=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if job is None:
            return False
        # The heartbeat must tick while ASR/DeepSeek block the main flow, so it
        # runs on its own thread with its own short-lived sessions.
        heartbeat = LeaseHeartbeat(
            job_id=job.job_id,
            renew=lambda: self.repository.renew_lease(
                job.job_id,
                lease_owner=self.worker_id,
                lease_seconds=self.lease_seconds,
            ),
            interval_seconds=self.heartbeat_seconds,
        )
        try:
            with heartbeat:
                self._process_job(job)
        except LeaseOwnershipLost:
            # Another worker legitimately reclaimed this job while we stalled.
            # Abandon the attempt rather than overwrite its work.
            logger.warning("lease ownership lost; abandoning attempt")
        return True

    def _run(self) -> None:
        while not self._stop_event.is_set():
            processed = self.process_once()
            if not processed:
                self._stop_event.wait(self.poll_interval_seconds)

    def _process_job(self, job: ProcessingJobRow) -> None:
        recording = self.repository.get_recording(job.recording_id)
        if recording is None:
            self.repository.fail_job(
                job.job_id,
                error_code="recording_missing",
                error_detail=f"recording {job.recording_id} does not exist",
            )
            return

        trace = ProcessingTrace(
            job_id=job.job_id,
            recording_id=recording.recording_id,
            family_id=recording.family_id,
            attempt=job.attempts + 1,
        )
        trace.instant(
            stage="job",
            event_name="job_claimed",
            attributes={"attempt": job.attempts + 1},
        )

        worker = self.repository.current_worker()
        if worker is None or worker.status != "ready":
            trace.instant(
                stage="asr_transcription",
                event_name="worker_unavailable",
                outcome=TraceOutcome.DEFERRED,
                attributes={"error_code": "asr_worker_unavailable"},
            )
            defer_recording_job(
                self.repository.database,
                job_id=job.job_id,
                error_code="asr_worker_unavailable",
                error_detail="no ready ASR worker is registered",
                retry_after_seconds=self.asr_retry_seconds,
                trace_events=trace.events,
                lease_owner=self.worker_id,
            )
            return

        trace.start("asr_transcription")
        try:
            with materialize_recording_audio(recording, self.storage) as audio_file:
                transcript = self.asr_client.transcribe(
                    worker_url=worker.url,
                    audio_path=audio_file,
                    recording_id=recording.recording_id,
                    content_type=recording.content_type,
                )
        except ASRClientError as exc:
            outcome = TraceOutcome.DEFERRED if exc.retryable else TraceOutcome.ERROR
            trace.finish(
                "asr_transcription",
                outcome=outcome,
                event_name="stage_deferred" if exc.retryable else "stage_failed",
                attributes={
                    "error_code": "asr_temporarily_unavailable" if exc.retryable else "asr_failed"
                },
            )
            if exc.retryable:
                defer_recording_job(
                    self.repository.database,
                    job_id=job.job_id,
                    error_code="asr_temporarily_unavailable",
                    error_detail=(
                        "ASR worker temporarily unavailable; inspect privacy-safe trace codes"
                    ),
                    retry_after_seconds=self.asr_retry_seconds,
                    trace_events=trace.events,
                    lease_owner=self.worker_id,
                )
            else:
                fail_recording_job(
                    self.repository.database,
                    job_id=job.job_id,
                    error_code="asr_failed",
                    error_detail="ASR transcription failed; inspect privacy-safe trace codes",
                    trace_events=trace.events,
                    lease_owner=self.worker_id,
                )
            return

        trace.finish(
            "asr_transcription",
            outcome=TraceOutcome.SUCCESS,
            attributes={
                "segment_count": len(transcript.segments),
                "duration_seconds": transcript.duration_seconds,
            },
        )

        status_by_stage = {
            "cleaning": JobStatus.CLEANING,
            "extracting": JobStatus.EXTRACTING,
            "resolving": JobStatus.RESOLVING,
            "planning_long_form": JobStatus.CLEANING,
            "merging_windows": JobStatus.EXTRACTING,
            "global_validation": JobStatus.EXTRACTING,
            "resolving_entities": JobStatus.RESOLVING,
        }
        active_pipeline_stage: str | None = None

        def report_stage(stage: str) -> None:
            nonlocal active_pipeline_stage
            if active_pipeline_stage is not None:
                trace.finish(active_pipeline_stage, outcome=TraceOutcome.SUCCESS)
            active_pipeline_stage = stage
            trace.start(stage)
            status = status_by_stage.get(stage)
            if status is None and stage.startswith("window_"):
                status = JobStatus.CLEANING if stage.endswith("_cleaning") else JobStatus.EXTRACTING
            if status is not None:
                self.repository.update_job_stage(
                    job.job_id, status, stage, lease_owner=self.worker_id
                )

        try:
            resolution_context = self.archive_repository.build_resolution_context(
                family_id=recording.family_id,
                speaker_id=recording.speaker_id,
            )
            trace.instant(
                stage="archive_context",
                event_name="context_loaded",
                attributes={"known_person_count": len(resolution_context.profiles)},
            )
            result = self.pipeline.process(
                PipelineRequest(
                    transcript=transcript,
                    speaker_id=recording.speaker_id,
                    speaker_name=recording.speaker_name,
                    known_people=[profile.person for profile in resolution_context.profiles],
                    # Reconstructed from the durable row: the upload request is
                    # long gone by the time the worker runs. NULL means a
                    # pre-migration recording, which reads as the defaults.
                    requested_audio_language=AudioLanguage(recording.audio_language or "auto"),
                    requested_output_language=OutputLanguage(
                        recording.output_language or "same_as_transcript"
                    ),
                ),
                stage_callback=report_stage,
                resolution_context=resolution_context,
            )
            if active_pipeline_stage is not None:
                trace.finish(active_pipeline_stage, outcome=TraceOutcome.SUCCESS)
                active_pipeline_stage = None

            result = result.model_copy(
                update={
                    "processing": {
                        **result.processing,
                        "trace_id": trace.trace_id,
                    }
                }
            )
            self.repository.update_job_stage(
                job.job_id,
                JobStatus.RESOLVING,
                "persisting_archive",
            )
            trace.start("archive_persistence")
            with self.repository.database.session_factory.begin() as session:
                self.conflict_resolution.persist_pipeline_result(
                    session,
                    recording=recording,
                    result=result,
                )
                persist_generic_claims(
                    session,
                    recording=recording,
                    result=result,
                )
                trace.finish(
                    "archive_persistence",
                    outcome=TraceOutcome.INFO,
                    event_name="transaction_prepared",
                    attributes=_pipeline_trace_attributes(result),
                )
                finalize_recording_job(
                    session,
                    job_id=job.job_id,
                    result=result,
                    trace_events=trace.events,
                    lease_owner=self.worker_id,
                )
        except Exception:
            trace.fail_active_stages(error_code="pipeline_failed")
            trace.instant(
                stage="job",
                event_name="job_failed",
                outcome=TraceOutcome.ERROR,
                attributes={"error_code": "pipeline_failed"},
            )
            fail_recording_job(
                self.repository.database,
                job_id=job.job_id,
                error_code="pipeline_failed",
                error_detail="pipeline processing failed; inspect privacy-safe trace codes",
                trace_events=trace.events,
                lease_owner=self.worker_id,
            )

    def wait_until_idle(self, timeout_seconds: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not self.process_once():
                return True
        return False


def _pipeline_trace_attributes(
    result: PipelineResult,
) -> dict[str, str | int | float | bool | None]:
    attributes: dict[str, str | int | float | bool | None] = {
        "pipeline_seconds": result.processing.get("total_seconds"),
        "people_count": len(result.extraction.people_mentions),
        "relationship_count": len(result.extraction.relationship_claims),
        "resolution_count": len(result.resolutions),
        "question_count": len(result.extraction.unresolved_questions),
    }
    for usage_name in ("cleaner_usage", "extractor_usage"):
        usage = result.processing.get(usage_name)
        if not isinstance(usage, dict):
            continue
        prefix = usage_name.removesuffix("_usage")
        for source_key, target_key in (
            ("prompt_tokens", "input_units"),
            ("completion_tokens", "output_units"),
            ("total_tokens", "total_units"),
        ):
            value = usage.get(source_key)
            if isinstance(value, (int, float)):
                attributes[f"{prefix}_{target_key}"] = value
    return attributes
