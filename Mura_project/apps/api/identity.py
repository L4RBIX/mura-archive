"""Identity and family foundation API.

Signing in and listing your own families need only a verified Principal, since
there is no family scope yet to authorize against. Everything addressed by
``family_id`` goes through the shared capability chain instead, so these routes
resolve membership exactly the same way the recording, profile and conflict
routes do -- one implementation, one place to get it wrong.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import Field

from apps.api.errors import SOLE_OWNER_REQUIRED
from mura.domain.models import StrictModel
from mura.identity.auth import Principal
from mura.identity.context import AuthorizedFamilyContext
from mura.identity.policy import Capability, FamilyRole, capabilities_for
from mura.storage.identity import (
    IdentityRepository,
    MembershipNotFoundError,
    SoleOwnerError,
)


class UserView(StrictModel):
    """Safe self-description. Provider subject and issuer are not exposed."""

    user_id: str
    email: str | None = None
    display_name: str | None = None


class FamilyView(StrictModel):
    family_id: str
    name: str
    #: The caller's own role, so the UI can hide actions it may not perform.
    role: FamilyRole
    capabilities: list[Capability] = Field(default_factory=list)


class MemberView(StrictModel):
    """Minimal member data: no email, no issuer, no provider subject."""

    user_id: str
    display_name: str | None = None
    role: FamilyRole


class CreateFamilyRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)


def _not_found() -> HTTPException:
    # A private family and a nonexistent one are the same answer.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


def register_identity_routes(
    app: FastAPI,
    *,
    principal_dependency: Callable[..., Principal],
    family_read_dependency: Callable[..., object],
    read_members_dependency: Callable[..., object],
    identity_repository_dependency: Callable[..., object],
) -> None:
    def _repository(runtime: object) -> IdentityRepository:
        return cast(IdentityRepository, runtime)

    @app.get("/v1/me", response_model=UserView)
    def get_me(
        principal: Principal = Depends(principal_dependency),
    ) -> UserView:
        return UserView(
            user_id=principal.user_id,
            email=principal.email,
            display_name=principal.display_name,
        )

    @app.post("/v1/families", response_model=FamilyView, status_code=201)
    def create_family(
        request: CreateFamilyRequest,
        principal: Principal = Depends(principal_dependency),
        repository: object = Depends(identity_repository_dependency),
    ) -> FamilyView:
        # The owner is the authenticated principal; the body cannot name one.
        family = _repository(repository).create_family(
            name=request.name, owner_user_id=principal.user_id
        )
        return FamilyView(
            family_id=family.family_id,
            name=family.name,
            role=FamilyRole.OWNER,
            capabilities=sorted(capabilities_for(FamilyRole.OWNER)),
        )

    @app.get("/v1/families", response_model=list[FamilyView])
    def list_families(
        principal: Principal = Depends(principal_dependency),
        repository: object = Depends(identity_repository_dependency),
    ) -> list[FamilyView]:
        # Membership-scoped: legacy families with no members are never listed.
        return [
            FamilyView(
                family_id=family.family_id,
                name=family.name,
                role=role,
                capabilities=sorted(capabilities_for(role)),
            )
            for family, role in _repository(repository).list_families_for_user(principal.user_id)
        ]

    @app.get("/v1/families/{family_id}", response_model=FamilyView)
    def get_family(
        family_id: str,
        context: object = Depends(family_read_dependency),
    ) -> FamilyView:
        # The shared context already resolved family and role in one query, so
        # the route reads them rather than looking membership up a second time.
        authorized = cast(AuthorizedFamilyContext, context)
        return FamilyView(
            family_id=authorized.family.family_id,
            name=authorized.family.name,
            role=authorized.role,
            capabilities=sorted(authorized.capabilities),
        )

    @app.get("/v1/families/{family_id}/members", response_model=list[MemberView])
    def list_members(
        family_id: str,
        context: object = Depends(read_members_dependency),
        repository: object = Depends(identity_repository_dependency),
    ) -> list[MemberView]:
        del context  # Membership and capability already proven.
        identity = _repository(repository)
        return [
            MemberView(
                user_id=user.user_id,
                display_name=user.display_name,
                role=FamilyRole(row.role),
            )
            for row, user in identity.list_members(family_id)
        ]


class UpdateMemberRoleRequest(StrictModel):
    role: FamilyRole


def register_membership_admin_routes(
    app: FastAPI,
    *,
    manage_members_dependency: Callable[..., object],
    identity_repository_dependency: Callable[..., object],
) -> None:
    """Owner-only membership administration.

    New in PR-03, so these are Principal-native from the start. Adding a member
    is deliberately absent: it needs an invitation lifecycle, and faking one by
    email would create memberships nobody agreed to.
    """

    @app.patch("/v1/families/{family_id}/members/{user_id}", response_model=MemberView)
    def update_member_role(
        family_id: str,
        user_id: str,
        request: UpdateMemberRoleRequest,
        context: object = Depends(manage_members_dependency),
        repository: object = Depends(identity_repository_dependency),
    ) -> MemberView:
        del context  # Authorization already proven by the dependency.
        identity = cast(IdentityRepository, repository)
        try:
            # The service checks the owner count under row locks; the route must
            # never re-implement a weaker version of that invariant.
            membership = identity.change_member_role(
                family_id=family_id, user_id=user_id, role=request.role
            )
        except MembershipNotFoundError as exc:
            raise _not_found() from exc
        except SoleOwnerError as exc:
            raise sole_owner_error() from exc
        user = identity.get_user(user_id)
        return MemberView(
            user_id=user_id,
            display_name=user.display_name if user else None,
            role=FamilyRole(membership.role),
        )

    @app.delete("/v1/families/{family_id}/members/{user_id}", status_code=204)
    def remove_member(
        family_id: str,
        user_id: str,
        context: object = Depends(manage_members_dependency),
        repository: object = Depends(identity_repository_dependency),
    ) -> None:
        del context
        identity = cast(IdentityRepository, repository)
        try:
            identity.remove_member(family_id=family_id, user_id=user_id)
        except MembershipNotFoundError as exc:
            # A membership outside this family is simply not found.
            raise _not_found() from exc
        except SoleOwnerError as exc:
            raise sole_owner_error() from exc


def sole_owner_error() -> HTTPException:
    """A distinguishable code: the client must explain *why* the change failed.

    "A family must always keep an owner" is actionable guidance, unlike a
    generic conflict, and it reveals nothing the caller -- already an owner of
    this family -- does not know.
    """

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=SOLE_OWNER_REQUIRED)


__all__ = [
    "CreateFamilyRequest",
    "FamilyView",
    "MemberView",
    "SoleOwnerError",
    "UserView",
    "register_identity_routes",
    "sole_owner_error",
]
