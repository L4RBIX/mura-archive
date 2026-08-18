from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from mura.domain.models import (
    LanguageContext,
    PipelineResult,
    StrictModel,
)

#: Stage used while Core is waiting to retry a recording by itself. A deferred
#: job is deliberately *not* a separate status: it stays QUEUED and carries this
#: stage plus the retry metadata, so the public status set stays minimal.
WAITING_FOR_ASR_STAGE = "waiting_for_asr"


class JobStatus(StrEnum):
    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    CLEANING = "cleaning"
    EXTRACTING = "extracting"
    RESOLVING = "resolving"
    COMPLETED = "completed"
    FAILED = "failed"


def resolve_retry_state(
    *,
    status: JobStatus,
    stage: str,
    next_attempt_at: datetime,
    now: datetime,
) -> tuple[bool, int | None, datetime | None]:
    """Retry metadata for a job.

    ``retryable`` means Core will retry this job automatically, with no user
    action and no public retry endpoint. Ordinary freshly queued work is not
    retryable: it has never failed and is simply waiting its turn. Only a job
    that Core itself deferred qualifies.
    """

    if status is not JobStatus.QUEUED or stage != WAITING_FOR_ASR_STAGE:
        return False, None, None
    remaining = math.ceil((next_attempt_at - now).total_seconds())
    return True, max(0, remaining), next_attempt_at


class RecordingAccepted(StrictModel):
    recording_id: str
    job_id: str
    status: JobStatus = JobStatus.QUEUED


class JobView(StrictModel):
    job_id: str
    recording_id: str
    status: JobStatus
    stage: str
    attempts: int = Field(ge=0)
    #: True only while Core will retry this job by itself.
    retryable: bool = False
    retry_after_seconds: int | None = Field(default=None, ge=0)
    next_retry_at: datetime | None = None
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class SpeakerResolution(StrEnum):
    """Whether Core can name a canonical archive person for the narrator."""

    #: speaker_person_id was supplied and verified against this family archive.
    RESOLVED = "resolved"
    #: No canonical person yet. Entity resolution may still materialise one.
    PENDING = "pending"


class SpeakerView(StrictModel):
    """Narrator identity as Core can actually vouch for it.

    ``person_id`` is a canonical archive person or None. An internal
    ``narrator_<recording_id>`` reference is never surfaced here: until entity
    resolution materialises a person, the honest answer is None.
    """

    person_id: str | None = None
    name: str
    resolution_status: SpeakerResolution = SpeakerResolution.PENDING


class RecordingResultView(StrictModel):
    """Public recording result.

    ``result`` intentionally carries the whole PipelineResult rather than a
    display projection, so evidence spans, provenance activities, conflict sets,
    assertion modes and resolution status survive the API boundary for Story,
    Person, Tree, Review, Ask MURA, Book and provenance inspection. No audio
    path, database row or provider payload is exposed.
    """

    recording_id: str
    family_id: str
    speaker: SpeakerView
    job: JobView
    language_context: LanguageContext
    result: PipelineResult


class ReviewItemsView(StrictModel):
    recording_id: str
    uncertain_fragments: list[dict[str, Any]] = Field(default_factory=list)
    detected_corrections: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_questions: list[dict[str, Any]] = Field(default_factory=list)
    extraction_issues: list[dict[str, Any]] = Field(default_factory=list)
    ambiguous_resolutions: list[dict[str, Any]] = Field(default_factory=list)
    conflict_sets: list[dict[str, Any]] = Field(default_factory=list)
