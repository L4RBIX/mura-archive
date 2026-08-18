"""Conflict review routes.

Reading a conflict needs ``read_conflicts``; resolving, dismissing and reopening
one is an archive mutation and needs ``resolve_conflicts``, which viewers do not
carry. The service layer is family-scoped underneath, so a conflict id belonging
to another family is not found rather than forbidden.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol, cast

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from mura.storage.conflict_resolution import (
    ConflictMutationResult,
    ConflictNotFoundError,
    ConflictResolutionError,
    ConflictReviewView,
)
from mura.storage.database import Database
from mura.storage.generic_review import UnifiedConflictReviewService


class RuntimeWithDatabase(Protocol):
    database: Database


class ConflictDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_reference: str = Field(min_length=1, max_length=256)
    note: str = Field(min_length=1, max_length=4000)


class ResolveConflictRequest(ConflictDecisionRequest):
    preferred_claim_id: str = Field(min_length=1, max_length=64)


def _service(runtime: object) -> UnifiedConflictReviewService:
    typed_runtime = cast(RuntimeWithDatabase, runtime)
    return UnifiedConflictReviewService(typed_runtime.database)


def _not_found(exc: ConflictNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _invalid_transition(exc: ConflictResolutionError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def register_conflict_routes(
    app: FastAPI,
    *,
    get_runtime_dependency: Callable[..., object],
    read_conflicts_dependency: Callable[..., object],
    resolve_conflicts_dependency: Callable[..., object],
) -> None:
    read = [Depends(read_conflicts_dependency)]
    mutate = [Depends(resolve_conflicts_dependency)]

    @app.get(
        "/v1/families/{family_id}/conflicts",
        response_model=list[ConflictReviewView],
        dependencies=read,
    )
    def list_family_conflicts(
        family_id: str,
        runtime: object = Depends(get_runtime_dependency),
        conflict_status: Literal["open", "resolved", "dismissed"] | None = Query(
            default=None,
            alias="status",
        ),
    ) -> list[ConflictReviewView]:
        return _service(runtime).list_conflicts(
            family_id=family_id,
            status=conflict_status,
        )

    @app.get(
        "/v1/families/{family_id}/conflicts/{conflict_id}",
        response_model=ConflictReviewView,
        dependencies=read,
    )
    def get_family_conflict(
        family_id: str,
        conflict_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> ConflictReviewView:
        try:
            return _service(runtime).get_conflict(
                family_id=family_id,
                conflict_id=conflict_id,
            )
        except ConflictNotFoundError as exc:
            raise _not_found(exc) from exc

    @app.post(
        "/v1/families/{family_id}/conflicts/{conflict_id}/resolve",
        response_model=ConflictMutationResult,
        dependencies=mutate,
    )
    def resolve_family_conflict(
        family_id: str,
        conflict_id: str,
        request: ResolveConflictRequest,
        runtime: object = Depends(get_runtime_dependency),
    ) -> ConflictMutationResult:
        try:
            return _service(runtime).resolve(
                family_id=family_id,
                conflict_id=conflict_id,
                preferred_claim_id=request.preferred_claim_id,
                reviewer_reference=request.reviewer_reference,
                note=request.note,
            )
        except ConflictNotFoundError as exc:
            raise _not_found(exc) from exc
        except ConflictResolutionError as exc:
            raise _invalid_transition(exc) from exc

    @app.post(
        "/v1/families/{family_id}/conflicts/{conflict_id}/dismiss",
        response_model=ConflictMutationResult,
        dependencies=mutate,
    )
    def dismiss_family_conflict(
        family_id: str,
        conflict_id: str,
        request: ConflictDecisionRequest,
        runtime: object = Depends(get_runtime_dependency),
    ) -> ConflictMutationResult:
        try:
            return _service(runtime).dismiss(
                family_id=family_id,
                conflict_id=conflict_id,
                reviewer_reference=request.reviewer_reference,
                note=request.note,
            )
        except ConflictNotFoundError as exc:
            raise _not_found(exc) from exc
        except ConflictResolutionError as exc:
            raise _invalid_transition(exc) from exc

    @app.post(
        "/v1/families/{family_id}/conflicts/{conflict_id}/reopen",
        response_model=ConflictMutationResult,
        dependencies=mutate,
    )
    def reopen_family_conflict(
        family_id: str,
        conflict_id: str,
        request: ConflictDecisionRequest,
        runtime: object = Depends(get_runtime_dependency),
    ) -> ConflictMutationResult:
        try:
            return _service(runtime).reopen(
                family_id=family_id,
                conflict_id=conflict_id,
                reviewer_reference=request.reviewer_reference,
                note=request.note,
            )
        except ConflictNotFoundError as exc:
            raise _not_found(exc) from exc
        except ConflictResolutionError as exc:
            raise _invalid_transition(exc) from exc
