from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from mura.domain.models import (
    CleanerResult,
    ExtractionResult,
    PipelineResult,
    RawSegment,
    ReadableSegment,
    TranscriptEnvelope,
)
from mura.jobs import JobStatus
from mura.observability import ProcessingTrace, TraceOutcome, TraceRepository
from mura.release_control import (
    CURRENT_RELEASE_ID,
    RELEASE_CONTROL_KEY,
    ReleaseControlRow,
)
from mura.storage.archive import ArchivePersonRow
from mura.storage.completion import finalize_recording_job
from mura.storage.database import Database, RecordingRepository

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL is required for the PostgreSQL integration smoke test",
)


def _result(recording_id: str) -> PipelineResult:
    transcript = TranscriptEnvelope(
        recording_id=recording_id,
        duration_seconds=1.0,
        full_text="synthetic postgres fixture",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=1,
                text="synthetic postgres fixture",
            )
        ],
        asr_model="fixture",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )
    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[
                ReadableSegment(segment_id="seg_001", text="Synthetic PostgreSQL fixture.")
            ],
            full_readable_text="Synthetic PostgreSQL fixture.",
        ),
        extraction=ExtractionResult(
            recording_id=recording_id,
            speaker_id="speaker_postgres",
            speaker_name="Synthetic Speaker",
        ),
        processing={"total_seconds": 0.1},
    )


def test_postgres_migration_and_atomic_completion(tmp_path: Path) -> None:
    assert POSTGRES_URL is not None
    suffix = uuid.uuid4().hex[:12]
    recording_id = f"rec_pg_{suffix}"
    job_id = f"job_pg_{suffix}"
    person_id = f"person_pg_{suffix}"

    database = Database(POSTGRES_URL)
    with database.session_factory() as session:
        release_control = session.get(ReleaseControlRow, RELEASE_CONTROL_KEY)
        assert release_control is not None
        assert release_control.active_release_id == CURRENT_RELEASE_ID
        assert release_control.generation == 1

    repository = RecordingRepository(database)
    audio_path = tmp_path / f"{recording_id}.wav"
    audio_path.write_bytes(b"audio")
    repository.create_recording_and_job(
        recording_id=recording_id,
        job_id=job_id,
        family_id="family_postgres",
        speaker_id="speaker_postgres",
        speaker_name="Synthetic Speaker",
        original_filename="story.wav",
        content_type="audio/wav",
        audio_path=audio_path,
    )
    assert repository.claim_next_job(lease_owner="worker_test", lease_seconds=300) is not None

    trace = ProcessingTrace(
        job_id=job_id,
        recording_id=recording_id,
        family_id="family_postgres",
        attempt=1,
    )
    trace.start("archive_persistence")
    trace.finish(
        "archive_persistence",
        outcome=TraceOutcome.INFO,
        event_name="transaction_prepared",
    )

    with pytest.raises(RuntimeError, match="force postgres rollback"):
        with database.session_factory.begin() as session:
            session.add(
                ArchivePersonRow(
                    person_id=person_id,
                    family_id="family_postgres",
                    canonical_name="Synthetic Person",
                    normalized_name="synthetic person",
                    aliases=[],
                    verified_aliases=[],
                    category="family_member",
                    relations_to_speakers={},
                    source_recording_ids=[recording_id],
                )
            )
            finalize_recording_job(
                session,
                job_id=job_id,
                result=_result(recording_id),
                trace_events=trace.events,
            )
            raise RuntimeError("force postgres rollback")

    assert repository.get_pipeline_result(recording_id) is None
    rolled_back_job = repository.get_job(job_id)
    assert rolled_back_job is not None
    assert rolled_back_job.status == JobStatus.TRANSCRIBING.value
    assert TraceRepository(database).get_job_trace(job_id=job_id) is None
    with database.session_factory() as session:
        assert (
            session.scalar(select(ArchivePersonRow).where(ArchivePersonRow.person_id == person_id))
            is None
        )

    with database.session_factory.begin() as session:
        session.add(
            ArchivePersonRow(
                person_id=person_id,
                family_id="family_postgres",
                canonical_name="Synthetic Person",
                normalized_name="synthetic person",
                aliases=[],
                verified_aliases=[],
                category="family_member",
                relations_to_speakers={},
                source_recording_ids=[recording_id],
            )
        )
        finalize_recording_job(
            session,
            job_id=job_id,
            result=_result(recording_id),
            trace_events=trace.events,
        )

    completed_job = repository.get_job(job_id)
    assert completed_job is not None
    assert completed_job.status == JobStatus.COMPLETED.value
    stored_result = repository.get_pipeline_result(recording_id)
    assert stored_result is not None
    assert stored_result.transcript == _result(recording_id).transcript
    assert stored_result.processing["release_id"] == CURRENT_RELEASE_ID
    budget = stored_result.processing["runtime_budget"]
    assert isinstance(budget, dict)
    assert budget["passed"] is True
    assert TraceRepository(database).get_job_trace(job_id=job_id) is not None
