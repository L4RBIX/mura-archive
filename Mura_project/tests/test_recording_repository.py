from __future__ import annotations

from pathlib import Path

from mura.domain.models import (
    CleanerResult,
    ExtractionResult,
    PipelineResult,
    RawSegment,
    ReadableSegment,
    TranscriptEnvelope,
)
from mura.jobs import JobStatus
from mura.storage.database import Database, RecordingRepository


def _result() -> PipelineResult:
    transcript = TranscriptEnvelope(
        recording_id="rec_1",
        duration_seconds=4.0,
        full_text="менің атым күләш",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=4,
                text="менің атым күләш",
            )
        ],
        asr_model="gigaam",
        asr_revision="large_ctc",
        chunker_version="silero-smart-v1",
    )
    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[ReadableSegment(segment_id="seg_001", text="Менің атым Күләш.")],
            full_readable_text="Менің атым Күләш.",
        ),
        extraction=ExtractionResult(
            recording_id="rec_1",
            speaker_id="speaker_1",
            speaker_name="Күләш",
        ),
        processing={"total_seconds": 1.25},
    )


def test_repository_persists_job_result_and_worker(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'mura.db'}")
    database.create_schema()
    repository = RecordingRepository(database)
    audio_path = tmp_path / "rec_1.m4a"
    audio_path.write_bytes(b"audio")

    repository.create_recording_and_job(
        recording_id="rec_1",
        job_id="job_1",
        family_id="family_1",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        original_filename="story.m4a",
        content_type="audio/mp4",
        audio_path=audio_path,
    )

    queued = repository.get_job("job_1")
    assert queued is not None
    assert queued.status == JobStatus.QUEUED.value

    claimed = repository.claim_next_job(lease_owner="worker_test", lease_seconds=300)
    assert claimed is not None
    assert claimed.job_id == "job_1"
    assert claimed.status == JobStatus.TRANSCRIBING.value

    repository.update_job_stage("job_1", JobStatus.CLEANING, "cleaning")
    repository.complete_job("job_1", _result())

    completed = repository.get_job("job_1")
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED.value
    assert repository.get_pipeline_result("rec_1") == _result()

    registered = repository.register_worker(
        url="https://example.trycloudflare.com/",
        status="ready",
    )
    assert registered.url == "https://example.trycloudflare.com"
    current = repository.current_worker()
    assert current is not None
    assert current.url == registered.url


def test_repository_defers_unavailable_asr_job(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'mura.db'}")
    database.create_schema()
    repository = RecordingRepository(database)
    audio_path = tmp_path / "rec_2.wav"
    audio_path.write_bytes(b"audio")
    repository.create_recording_and_job(
        recording_id="rec_2",
        job_id="job_2",
        family_id="family_1",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        original_filename="story.wav",
        content_type="audio/wav",
        audio_path=audio_path,
    )
    assert repository.claim_next_job(lease_owner="worker_test", lease_seconds=300) is not None

    repository.defer_job(
        "job_2",
        error_code="asr_worker_unavailable",
        error_detail="worker is offline",
        retry_after_seconds=60,
    )

    job = repository.get_job("job_2")
    assert job is not None
    assert job.status == JobStatus.QUEUED.value
    assert job.stage == "waiting_for_asr"
    assert job.attempts == 1
    assert repository.claim_next_job(lease_owner="worker_test", lease_seconds=300) is None
