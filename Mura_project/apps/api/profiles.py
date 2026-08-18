from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

from fastapi import Depends, FastAPI, HTTPException, status

from mura.storage.database import Database
from mura.storage.generic_review import GenericProfileRepository
from mura.storage.profile_models import PersonProfileView, ProfileNotFoundError


class RuntimeWithDatabase(Protocol):
    database: Database


def _repository(runtime: object) -> GenericProfileRepository:
    typed_runtime = cast(RuntimeWithDatabase, runtime)
    return GenericProfileRepository(typed_runtime.database)


def register_profile_routes(
    app: FastAPI,
    *,
    get_runtime_dependency: Callable[..., object],
    read_profiles_dependency: Callable[..., object],
) -> None:
    """Reading the archive is a viewer capability.

    There is no profile mutation route to guard: profiles are derived from
    evidence by entity resolution, not edited over HTTP, so inventing a
    narrower-than-viewer restriction here would protect nothing.
    """

    dependencies = [Depends(read_profiles_dependency)]

    @app.get(
        "/v1/families/{family_id}/profiles",
        response_model=list[PersonProfileView],
        dependencies=dependencies,
    )
    def list_family_profiles(
        family_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> list[PersonProfileView]:
        return _repository(runtime).list_profiles(family_id=family_id)

    @app.get(
        "/v1/families/{family_id}/profiles/{person_id}",
        response_model=PersonProfileView,
        dependencies=dependencies,
    )
    def get_family_profile(
        family_id: str,
        person_id: str,
        runtime: object = Depends(get_runtime_dependency),
    ) -> PersonProfileView:
        try:
            return _repository(runtime).get_profile(
                family_id=family_id,
                person_id=person_id,
            )
        except ProfileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
