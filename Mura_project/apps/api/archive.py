"""The family archive, as the product reads it.

Every route here is family-scoped and Principal-native: a verified user, a
membership row, then a capability. Scoping is a predicate inside the query, so
a resource belonging to another family is never selected -- not selected and
then compared, which is how an id becomes a probe.

Capabilities are reused rather than invented. Reading people and the graph is
`read_profiles`, reading stories is `read_recordings` because a story is
recording-derived content, and the review queue is `read_review`. Adding a
capability per endpoint would have meant a policy change for no gain in
expressiveness.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Protocol, cast

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from apps.api.errors import FAMILY_NOT_FOUND
from mura.storage.archive_read import (
    ArchiveOverviewView,
    ArchiveReadRepository,
    ArchiveResourceNotFound,
    PersonSummaryView,
    RelationshipView,
    ReviewItemView,
    StoryDetailView,
    StoryPageView,
)
from mura.storage.audio import AudioStorage
from mura.storage.database import Database, RecordingRow


class RuntimeWithDatabase(Protocol):
    database: Database
    storage: AudioStorage


def _repository(runtime: object) -> ArchiveReadRepository:
    return ArchiveReadRepository(cast(RuntimeWithDatabase, runtime).database)


def _not_found() -> HTTPException:
    """Absent and not-yours are the same answer, and say nothing further."""

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FAMILY_NOT_FOUND)


def register_archive_routes(
    app: FastAPI,
    *,
    get_runtime_dependency: Callable[..., object],
    read_family_dependency: Callable[..., object],
    read_profiles_dependency: Callable[..., object],
    read_recordings_dependency: Callable[..., object],
    read_review_dependency: Callable[..., object],
) -> None:
    @app.get(
        "/v1/families/{family_id}/archive",
        response_model=ArchiveOverviewView,
        dependencies=[Depends(read_family_dependency)],
    )
    def get_family_archive(
        family_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> ArchiveOverviewView:
        """Counts and the newest few stories.

        Everything here is a real count of persisted rows. An archive with
        nothing in it returns zeros, which is what lets the product show an
        honest empty state instead of a demonstration family.
        """

        return _repository(runtime).overview(family_id=family_id)

    @app.get(
        "/v1/families/{family_id}/people",
        response_model=list[PersonSummaryView],
        dependencies=[Depends(read_profiles_dependency)],
    )
    def list_family_people(
        family_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> list[PersonSummaryView]:
        return _repository(runtime).list_people(family_id=family_id)

    @app.get(
        "/v1/families/{family_id}/relationships",
        response_model=list[RelationshipView],
        dependencies=[Depends(read_profiles_dependency)],
    )
    def list_family_relationships(
        family_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> list[RelationshipView]:
        """The materialized graph only.

        A relationship claim that did not clear the evidence bar when the
        archive was written is not here, and must not be drawn as a confident
        line between two people because a model once proposed it.
        """

        return _repository(runtime).list_relationships(family_id=family_id)

    @app.get(
        "/v1/families/{family_id}/stories",
        response_model=StoryPageView,
        dependencies=[Depends(read_recordings_dependency)],
    )
    def list_family_stories(
        family_id: str,
        runtime: object = Depends(get_runtime_dependency),
        limit: Annotated[int | None, Query(ge=1, le=100)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> StoryPageView:
        """Bounded by construction.

        A family archive is meant to grow for years, so this pages rather than
        returning everything, and each item carries a trimmed excerpt: a list
        endpoint must not become a way to pull every transcript at once.
        """

        return _repository(runtime).list_stories(
            family_id=family_id,
            limit=limit,
            offset=offset,
        )

    @app.get(
        "/v1/families/{family_id}/stories/{story_id}",
        response_model=StoryDetailView,
        dependencies=[Depends(read_recordings_dependency)],
    )
    def get_family_story(
        family_id: str,
        story_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> StoryDetailView:
        try:
            return _repository(runtime).get_story(family_id=family_id, story_id=story_id)
        except ArchiveResourceNotFound as exc:
            raise _not_found() from exc

    @app.get(
        "/v1/families/{family_id}/recordings/{recording_id}/audio",
        dependencies=[Depends(read_recordings_dependency)],
        response_class=StreamingResponse,
    )
    def get_family_recording_audio(
        family_id: str,
        recording_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> StreamingResponse:
        """The recording itself, to an authorised family member.

        This exists so the product can stop pretending. A story page with a
        waveform and a play button over audio that was never retrievable is a
        lie about the archive; either the family can hear the recording or the
        page says it cannot.

        The storage key never leaves the server. It is resolved from a row that
        was already constrained to this family, handed to the AudioStorage
        protocol, and the response carries only bytes and a content type -- no
        path, no key, no backend name. A legacy row without a storage key is
        treated as absent rather than reaching for its filesystem path.
        """

        typed = cast(RuntimeWithDatabase, runtime)
        with typed.database.session_factory() as session:
            row = session.get(RecordingRow, recording_id)
            # Family scope is checked before anything is read from storage.
            if row is None or row.family_id != family_id or not row.storage_key:
                raise _not_found()
            storage_key = row.storage_key
            media_type = row.audio_mime_type or "application/octet-stream"

        try:
            stream = typed.storage.open(storage_key)
        except Exception as exc:
            # A missing object is not a different answer from a missing row:
            # both mean the family cannot hear this recording.
            raise _not_found() from exc

        return StreamingResponse(
            stream,
            media_type=media_type,
            headers={
                # Family audio must never sit in a shared cache.
                "cache-control": "no-store, private",
                "content-disposition": "inline",
            },
        )

    @app.get(
        "/v1/families/{family_id}/review-items",
        response_model=list[ReviewItemView],
        dependencies=[Depends(read_review_dependency)],
    )
    def list_family_review_items(
        family_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> list[ReviewItemView]:
        """What the archive says it cannot settle.

        Open questions and detected conflicts, both persisted. There is no
        client-side rule about what counts as uncertain -- putting that
        definition in a browser is how "needs review" quietly becomes whatever
        the UI finds convenient.
        """

        return _repository(runtime).list_review_items(family_id=family_id)
