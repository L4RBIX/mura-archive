from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from mura.observability import JobTraceView, TraceRepository
from mura.release_control import (
    ReleaseControlError,
    ReleaseControlService,
    ReleaseMutationResult,
    ReleaseStateView,
)
from mura.replay import FamilyReplayReport, FamilyReplayService, ReplayNotFoundError
from mura.retention import (
    RetentionConfirmationError,
    RetentionReport,
    RetentionService,
)
from mura.storage.database import Database, RecordingRepository


class RuntimeWithDatabase(Protocol):
    database: Database
    repository: RecordingRepository


class ReleaseActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_id: str = Field(min_length=1, max_length=96)
    requested_by: str = Field(min_length=1, max_length=256)
    note: str = Field(min_length=1, max_length=4000)


class ReleaseRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_by: str = Field(min_length=1, max_length=256)
    note: str = Field(min_length=1, max_length=4000)


class RetentionApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str = Field(min_length=1, max_length=128)


def _database(runtime: object) -> Database:
    return cast(RuntimeWithDatabase, runtime).database


def register_operations_routes(
    app: FastAPI,
    *,
    get_runtime_dependency: Callable[..., object],
    core_token_dependency: Callable[..., None],
    operations_token_dependency: Callable[..., None],
) -> None:
    """Service-internal and operator surfaces. No user principal reaches these.

    Job traces and deterministic family replay are engineering tooling on the
    application token: they expose stage timings, attempt history and evaluation
    output that no family role should read, so membership never grants them.
    Destructive operator routes require the separate operations credential --
    that dependency is mandatory, because defaulting it to the application token
    would silently re-merge the credential split PR-02C established.
    """

    dependencies = [Depends(core_token_dependency)]
    operations = [Depends(operations_token_dependency)]

    @app.get(
        "/v1/jobs/{job_id}/trace",
        response_model=JobTraceView,
        dependencies=dependencies,
    )
    def get_job_trace(
        job_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> JobTraceView:
        typed_runtime = cast(RuntimeWithDatabase, runtime)
        if typed_runtime.repository.get_job(job_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="job not found",
            )
        trace = TraceRepository(typed_runtime.database).get_job_trace(job_id=job_id)
        if trace is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="job trace is not available yet",
            )
        return trace

    @app.get(
        "/v1/operations/release",
        response_model=ReleaseStateView,
        dependencies=operations,
    )
    def get_release_state(
        runtime: object = Depends(get_runtime_dependency),
    ) -> ReleaseStateView:
        return ReleaseControlService(_database(runtime)).get_state()

    @app.post(
        "/v1/operations/release/activate",
        response_model=ReleaseMutationResult,
        dependencies=operations,
    )
    def activate_release(
        request: ReleaseActivateRequest,
        runtime: object = Depends(get_runtime_dependency),
    ) -> ReleaseMutationResult:
        try:
            return ReleaseControlService(_database(runtime)).activate(
                release_id=request.release_id,
                requested_by=request.requested_by,
                note=request.note,
            )
        except ReleaseControlError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    @app.post(
        "/v1/operations/release/rollback",
        response_model=ReleaseMutationResult,
        dependencies=operations,
    )
    def rollback_release(
        request: ReleaseRollbackRequest,
        runtime: object = Depends(get_runtime_dependency),
    ) -> ReleaseMutationResult:
        try:
            return ReleaseControlService(_database(runtime)).rollback(
                requested_by=request.requested_by,
                note=request.note,
            )
        except ReleaseControlError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    @app.post(
        "/v1/families/{family_id}/replays",
        response_model=FamilyReplayReport,
        dependencies=dependencies,
    )
    def replay_family(
        family_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> FamilyReplayReport:
        try:
            return FamilyReplayService(_database(runtime)).run(family_id=family_id)
        except ReplayNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/families/{family_id}/replays",
        response_model=list[FamilyReplayReport],
        dependencies=dependencies,
    )
    def list_family_replays(
        family_id: str,
        runtime: object = Depends(get_runtime_dependency),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[FamilyReplayReport]:
        return FamilyReplayService(_database(runtime)).list_runs(
            family_id=family_id,
            limit=limit,
        )

    @app.get(
        "/v1/operations/retention",
        response_model=RetentionReport,
        dependencies=operations,
    )
    def preview_retention(
        runtime: object = Depends(get_runtime_dependency),
    ) -> RetentionReport:
        return RetentionService(_database(runtime)).preview()

    @app.post(
        "/v1/operations/retention/apply",
        response_model=RetentionReport,
        dependencies=operations,
    )
    def apply_retention(
        request: RetentionApplyRequest,
        runtime: object = Depends(get_runtime_dependency),
    ) -> RetentionReport:
        try:
            return RetentionService(_database(runtime)).apply(confirmation=request.confirmation)
        except RetentionConfirmationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
