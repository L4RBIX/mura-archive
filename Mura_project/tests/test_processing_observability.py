from __future__ import annotations

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
from mura.observability import (
    ProcessingTrace,
    TraceOutcome,
    TraceRepository,
    sanitize_trace_attributes,
)
from mura.release_control import CURRENT_RELEASE_ID
from mura.storage.archive import ArchivePersonRow
from mura.storage.completion import finalize_recording_job
from mura.storage.database import Database, RecordingRepository


def _result() -> PipelineResult:
    transcript = TranscriptEnvelope(
        recording_id="rec_trace",
        duration_seconds=2.0,
        full_text="synthetic fixture",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=2,
                text="synthetic fixture",
            )
        ],
        asr_model="fixture",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )
    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[ReadableSegment(segment_id="seg_001", text="Synthetic fixture.")],
            full_readable_text="Synthetic fixture.",
        ),
        extraction=ExtractionResult(
            recording_id="rec_trace",
            speaker_id="speaker_1",
            speaker_name="Speaker",
        ),
        processing={"total_seconds": 0.25, "trace_id": "trace_trace"},
    )


def _repository(tmp_path: Path) -> tuple[Database, RecordingRepository]:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'mura.db'}")
    database.create_schema()
    repository = RecordingRepository(database)
    audio_path = tmp_path / "rec_trace.wav"
    audio_path.write_bytes(b"audio")
    repository.create_recording_and_job(
        recording_id="rec_trace",
        job_id="job_trace",
        family_id="family_1",
        speaker_id="speaker_1",
        speaker_name="Speaker",
        original_filename="story.wav",
        content_type="audio/wav",
        audio_path=audio_path,
    )
    assert repository.claim_next_job(lease_owner="worker_test", lease_seconds=300) is not None
    return database, repository


def _trace() -> ProcessingTrace:
    trace = ProcessingTrace(
        job_id="job_trace",
        recording_id="rec_trace",
        family_id="family_1",
        attempt=1,
    )
    trace.instant(
        stage="job",
        event_name="job_claimed",
        attributes={"attempt": 1},
    )
    trace.start("archive_persistence")
    trace.finish(
        "archive_persistence",
        outcome=TraceOutcome.INFO,
        event_name="transaction_prepared",
    )
    return trace


def test_trace_attributes_drop_sensitive_payloads() -> None:
    sanitized = sanitize_trace_attributes(
        {
            "segment_count": 4,
            "transcript_text": "private story",
            "speaker_name": "Private Person",
            "authorization": "Bearer secret",
            "error_code": "pipeline_failed",
        }
    )

    assert sanitized == {
        "segment_count": 4,
        "error_code": "pipeline_failed",
    }


def test_atomic_completion_rolls_back_archive_result_job_and_trace(tmp_path: Path) -> None:
    database, repository = _repository(tmp_path)
    trace = _trace()

    with pytest.raises(RuntimeError, match="force rollback"):
        with database.session_factory.begin() as session:
            session.add(
                ArchivePersonRow(
                    person_id="person_1",
                    family_id="family_1",
                    canonical_name="Synthetic Person",
                    normalized_name="synthetic person",
                    aliases=[],
                    verified_aliases=[],
                    category="family_member",
                    relations_to_speakers={},
                    source_recording_ids=["rec_trace"],
                )
            )
            finalize_recording_job(
                session,
                job_id="job_trace",
                result=_result(),
                trace_events=trace.events,
            )
            raise RuntimeError("force rollback")

    assert repository.get_pipeline_result("rec_trace") is None
    job = repository.get_job("job_trace")
    assert job is not None
    assert job.status == JobStatus.TRANSCRIBING.value
    assert TraceRepository(database).get_job_trace(job_id="job_trace") is None
    with database.session_factory() as session:
        assert (
            session.scalar(select(ArchivePersonRow).where(ArchivePersonRow.person_id == "person_1"))
            is None
        )


def test_atomic_completion_persists_result_job_archive_and_trace(tmp_path: Path) -> None:
    database, repository = _repository(tmp_path)
    trace = _trace()

    with database.session_factory.begin() as session:
        session.add(
            ArchivePersonRow(
                person_id="person_1",
                family_id="family_1",
                canonical_name="Synthetic Person",
                normalized_name="synthetic person",
                aliases=[],
                verified_aliases=[],
                category="family_member",
                relations_to_speakers={},
                source_recording_ids=["rec_trace"],
            )
        )
        finalize_recording_job(
            session,
            job_id="job_trace",
            result=_result(),
            trace_events=trace.events,
        )

    stored_result = repository.get_pipeline_result("rec_trace")
    assert stored_result is not None
    assert stored_result.transcript == _result().transcript
    assert stored_result.extraction == _result().extraction
    assert stored_result.processing["release_id"] == CURRENT_RELEASE_ID
    budget = stored_result.processing["runtime_budget"]
    assert isinstance(budget, dict)
    assert budget["passed"] is True
    assert budget["complete"] is False
    job = repository.get_job("job_trace")
    assert job is not None
    assert job.status == JobStatus.COMPLETED.value

    stored_trace = TraceRepository(database).get_job_trace(job_id="job_trace")
    assert stored_trace is not None
    assert stored_trace.trace_id == "trace_trace"
    assert stored_trace.attempts == [1]
    assert [event.event_name for event in stored_trace.events] == [
        "job_claimed",
        "transaction_prepared",
    ]
    assert stored_trace.stage_durations_ms["archive_persistence"] >= 0
