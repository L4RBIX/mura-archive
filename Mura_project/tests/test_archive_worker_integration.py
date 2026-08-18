from __future__ import annotations

from pathlib import Path
from typing import cast

from mura.asr import RemoteASRClient
from mura.domain.models import (
    CleanerResult,
    ExtractionResult,
    MentionResolution,
    PersonCategory,
    PersonMention,
    PipelineRequest,
    PipelineResult,
    RawSegment,
    ReadableSegment,
    ResolutionStatus,
    TranscriptEnvelope,
)
from mura.entity_resolution import EntityResolutionContext
from mura.orchestration.recordings import RecordingJobWorker
from mura.pipeline import MuraPipeline
from mura.storage.archive import ArchiveRepository
from mura.storage.database import Database, RecordingRepository


class _FakeASR:
    def transcribe(
        self,
        *,
        worker_url: str,
        audio_path: Path,
        recording_id: str,
        content_type: str | None,
    ) -> TranscriptEnvelope:
        del worker_url, audio_path, content_type
        text = "Ерлан туралы әңгіме."
        return TranscriptEnvelope(
            recording_id=recording_id,
            duration_seconds=4,
            language_hints=["kk"],
            full_text=text,
            segments=[RawSegment(segment_id="seg_001", start=0, end=4, text=text)],
            asr_model="fake-asr",
            asr_revision="fixture-v1",
            chunker_version="fixture-v1",
        )


class _ArchiveAwarePipeline:
    def __init__(self) -> None:
        self.context_sizes: list[int] = []
        self.person_ids: list[str | None] = []

    def process(
        self,
        request: PipelineRequest,
        *,
        stage_callback=None,
        resolution_context: EntityResolutionContext | None = None,
    ) -> PipelineResult:
        if stage_callback is not None:
            stage_callback("cleaning")
            stage_callback("extracting")
            stage_callback("resolving")
        context = resolution_context or EntityResolutionContext(family_id="family_1")
        self.context_sizes.append(len(context.profiles))
        existing_person_id = context.profiles[0].person.person_id if context.profiles else None
        self.person_ids.append(existing_person_id)
        mention = PersonMention(
            mention_id="mention_erlan",
            name="Ерлан",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="son",
            source_segment_ids=["seg_001"],
            confidence=1,
        )
        resolution = (
            MentionResolution(
                mention_id=mention.mention_id,
                status=ResolutionStatus.RESOLVED,
                person_id=existing_person_id,
                candidate_person_ids=[existing_person_id],
                reason="archive context matched fixture identity",
            )
            if existing_person_id is not None
            else MentionResolution(
                mention_id=mention.mention_id,
                status=ResolutionStatus.NEW_PERSON,
                reason="first archive recording",
            )
        )
        text = request.transcript.full_text
        return PipelineResult(
            transcript=request.transcript,
            cleaned_transcript=CleanerResult(
                readable_segments=[ReadableSegment(segment_id="seg_001", text=text)],
                full_readable_text=text,
            ),
            extraction=ExtractionResult(
                recording_id=request.transcript.recording_id,
                speaker_id=request.speaker_id,
                speaker_name=request.speaker_name,
                people_mentions=[mention],
            ),
            resolutions=[resolution],
        )


def _queue_recording(
    repository: RecordingRepository,
    *,
    tmp_path: Path,
    recording_id: str,
) -> None:
    audio_path = tmp_path / f"{recording_id}.wav"
    audio_path.write_bytes(b"audio")
    repository.create_recording_and_job(
        recording_id=recording_id,
        job_id=f"job_{recording_id}",
        family_id="family_1",
        speaker_id="speaker_1",
        speaker_name="Күләш",
        original_filename=audio_path.name,
        content_type="audio/wav",
        audio_path=audio_path,
    )


def test_worker_loads_archive_context_and_persists_followup_recording(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'worker.db'}")
    database.create_schema()
    repository = RecordingRepository(database)
    archive = ArchiveRepository(database)
    repository.register_worker(url="https://worker.example", status="ready")
    pipeline = _ArchiveAwarePipeline()
    worker = RecordingJobWorker(
        repository=repository,
        pipeline=cast(MuraPipeline, pipeline),
        asr_client=cast(RemoteASRClient, _FakeASR()),
    )

    _queue_recording(repository, tmp_path=tmp_path, recording_id="rec_1")
    assert worker.process_once() is True
    assert pipeline.context_sizes == [0]
    people_after_first = archive.list_people("family_1")
    assert len(people_after_first) == 1

    _queue_recording(repository, tmp_path=tmp_path, recording_id="rec_2")
    assert worker.process_once() is True
    assert pipeline.context_sizes == [0, 1]
    assert pipeline.person_ids[1] == people_after_first[0].person_id
    assert len(archive.list_people("family_1")) == 1
    assert len(archive.list_claims("family_1")) == 2
    assert repository.get_pipeline_result("rec_2") is not None
