"""Canonical family-scoped recording API.

``family_id`` is the resource scope and lives in the path, never in the body.

Authorization is two independent layers, and both must hold. The capability
dependency proves the caller is a member of the family in the path with a role
that carries the required capability. Every lookup below is then family-scoped in
the repository query itself, so a recording, job or review set belonging to
another family is simply not found -- membership in one family never reaches a
resource id that belongs to a different one.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import PurePath
from typing import Annotated, Any, Protocol, cast

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status

from mura.domain.models import (
    AudioLanguage,
    OutputLanguage,
    PipelineResult,
    ResolutionStatus,
    build_language_context,
)
from mura.jobs import (
    JobView,
    RecordingAccepted,
    RecordingResultView,
    ReviewItemsView,
    SpeakerResolution,
    SpeakerView,
)
from mura.speaker import (
    SpeakerSyntaxError,
    internal_narrator_reference,
    public_person_id,
    validate_speaker_person_id,
)
from mura.storage.audio import AudioStorage, AudioStorageError, AudioTooLargeError
from mura.storage.database import ProcessingJobRow, RecordingRow


class RecordingRepositoryProtocol(Protocol):
    """The family-scoped repository surface these routes rely on."""

    def family_person_exists(self, *, family_id: str, person_id: str) -> bool: ...

    def get_family_recording(self, *, family_id: str, recording_id: str) -> RecordingRow | None: ...

    def get_family_job(self, *, family_id: str, job_id: str) -> ProcessingJobRow | None: ...

    def get_family_job_for_recording(
        self, *, family_id: str, recording_id: str
    ) -> ProcessingJobRow | None: ...

    def get_family_pipeline_result(
        self, *, family_id: str, recording_id: str
    ) -> PipelineResult | None: ...

    def create_recording_and_job(self, **kwargs: Any) -> None: ...


class RecordingRuntime(Protocol):
    """Structural view of the pieces of CoreRuntime these routes need."""

    repository: RecordingRepositoryProtocol
    storage: AudioStorage


def _repository(runtime: object) -> RecordingRepositoryProtocol:
    return cast(RecordingRuntime, runtime).repository


def _not_found() -> HTTPException:
    # One shape for every miss: absent, or owned by another family.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


def resolve_speaker_reference(
    *,
    repository: RecordingRepositoryProtocol,
    family_id: str,
    recording_id: str,
    speaker_person_id: str | None,
) -> str:
    """Return the value to store in RecordingRow.speaker_id.

    A supplied id must be canonical in syntax *and* exist in this family.
    Otherwise the narrator is not canonical yet and gets a reserved internal
    reference; entity resolution stays responsible for materialising a person.
    """

    if speaker_person_id is None or not speaker_person_id.strip():
        return internal_narrator_reference(recording_id)

    try:
        candidate = validate_speaker_person_id(speaker_person_id)
    except SpeakerSyntaxError as exc:
        raise HTTPException(status_code=422, detail="invalid speaker_person_id") from exc

    if not repository.family_person_exists(family_id=family_id, person_id=candidate):
        # Nonexistent and other-family are the same answer on purpose.
        raise _not_found()
    return candidate


def _speaker_view(row: RecordingRow) -> SpeakerView:
    """Never surfaces the internal narrator reference as a canonical person."""

    canonical = public_person_id(row.speaker_id)
    return SpeakerView(
        person_id=canonical,
        name=row.speaker_name,
        resolution_status=(
            SpeakerResolution.RESOLVED if canonical is not None else SpeakerResolution.PENDING
        ),
    )


def register_recording_routes(
    app: FastAPI,
    *,
    get_runtime_dependency: Callable[..., object],
    create_recording_dependency: Callable[..., object],
    read_recordings_dependency: Callable[..., object],
    read_review_dependency: Callable[..., object],
    read_jobs_dependency: Callable[..., object],
    job_view_builder: Callable[[ProcessingJobRow], JobView],
) -> None:
    """Each route names the capability it needs; none accepts a service token."""

    @app.post(
        "/v1/families/{family_id}/recordings",
        response_model=RecordingAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(create_recording_dependency)],
    )
    def create_family_recording(
        family_id: str,
        file: Annotated[UploadFile, File(...)],
        speaker_name: Annotated[str, Form(min_length=1, max_length=256)],
        audio_language: Annotated[AudioLanguage, Form()] = AudioLanguage.AUTO,
        output_language: Annotated[OutputLanguage, Form()] = OutputLanguage.SAME_AS_TRANSCRIPT,
        speaker_person_id: Annotated[str | None, Form()] = None,
        runtime: object = Depends(get_runtime_dependency),
    ) -> RecordingAccepted:
        repository = _repository(runtime)
        recording_id = f"rec_{uuid.uuid4().hex}"
        job_id = f"job_{uuid.uuid4().hex}"
        speaker_reference = resolve_speaker_reference(
            repository=repository,
            family_id=family_id,
            recording_id=recording_id,
            speaker_person_id=speaker_person_id,
        )
        original_filename = PurePath(file.filename or "audio.bin").name

        storage: AudioStorage = cast(RecordingRuntime, runtime).storage
        try:
            file.file.seek(0)
            stored = storage.save(
                family_id=family_id,
                recording_id=recording_id,
                original_filename=original_filename,
                content_type=file.content_type,
                source=file.file,
            )
        except AudioTooLargeError as exc:
            raise HTTPException(status_code=413, detail="upload rejected") from exc
        except AudioStorageError as exc:
            raise HTTPException(status_code=415, detail="upload rejected") from exc

        try:
            repository.create_recording_and_job(
                recording_id=recording_id,
                job_id=job_id,
                family_id=family_id,
                speaker_id=speaker_reference,
                speaker_name=speaker_name,
                original_filename=original_filename,
                content_type=stored.content_type,
                audio_path=stored.storage_key,
                storage_key=stored.storage_key,
                storage_backend=stored.backend.value,
                audio_sha256=stored.sha256,
                audio_size_bytes=stored.size_bytes,
                audio_mime_type=stored.content_type,
                audio_language=audio_language.value,
                output_language=output_language.value,
            )
        except Exception:
            # The object is durable but the recording is not; drop the orphan.
            storage.delete(stored.storage_key)
            raise

        return RecordingAccepted(recording_id=recording_id, job_id=job_id)

    @app.get(
        "/v1/families/{family_id}/recordings/{recording_id}",
        response_model=RecordingResultView,
        dependencies=[Depends(read_recordings_dependency)],
    )
    def get_family_recording_result(
        family_id: str,
        recording_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> RecordingResultView:
        repository = _repository(runtime)
        recording = repository.get_family_recording(
            family_id=family_id,
            recording_id=recording_id,
        )
        if recording is None:
            raise _not_found()
        job = repository.get_family_job_for_recording(
            family_id=family_id,
            recording_id=recording_id,
        )
        if job is None:
            raise _not_found()
        result = repository.get_family_pipeline_result(
            family_id=family_id,
            recording_id=recording_id,
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="recording processing is not completed",
            )
        return RecordingResultView(
            recording_id=recording.recording_id,
            family_id=recording.family_id,
            speaker=_speaker_view(recording),
            job=job_view_builder(job),
            language_context=build_language_context(
                requested_audio_language=AudioLanguage(recording.audio_language or "auto"),
                requested_output_language=OutputLanguage(
                    recording.output_language or "same_as_transcript"
                ),
            ),
            result=result,
        )

    @app.get(
        "/v1/families/{family_id}/recordings/{recording_id}/review-items",
        response_model=ReviewItemsView,
        dependencies=[Depends(read_review_dependency)],
    )
    def get_family_review_items(
        family_id: str,
        recording_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> ReviewItemsView:
        repository = _repository(runtime)
        result = repository.get_family_pipeline_result(
            family_id=family_id,
            recording_id=recording_id,
        )
        if result is None:
            raise _not_found()

        extractor_usage = result.processing.get("extractor_usage", {})
        extraction_issues = (
            extractor_usage.get("extraction_issues", [])
            if isinstance(extractor_usage, dict)
            else []
        )
        return ReviewItemsView(
            recording_id=recording_id,
            uncertain_fragments=[
                item.model_dump(mode="json")
                for item in result.cleaned_transcript.uncertain_fragments
            ],
            detected_corrections=[
                item.model_dump(mode="json")
                for item in result.cleaned_transcript.detected_corrections
            ],
            unresolved_questions=[
                item.model_dump(mode="json") for item in result.extraction.unresolved_questions
            ],
            extraction_issues=(extraction_issues if isinstance(extraction_issues, list) else []),
            ambiguous_resolutions=[
                item.model_dump(mode="json")
                for item in result.resolutions
                if item.status == ResolutionStatus.NEEDS_REVIEW
            ],
            conflict_sets=[
                item.model_dump(mode="json") for item in result.extraction.conflict_sets
            ],
        )

    @app.get(
        "/v1/families/{family_id}/jobs/{job_id}",
        response_model=JobView,
        dependencies=[Depends(read_jobs_dependency)],
    )
    def get_family_job(
        family_id: str,
        job_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> JobView:
        job = _repository(runtime).get_family_job(
            family_id=family_id,
            job_id=job_id,
        )
        if job is None:
            raise _not_found()
        return job_view_builder(job)
