"""FastAPI wiring for family authorization.

The chain is deliberately linear and reusable, so PR-03B-SWITCH can apply it to
existing routes mechanically rather than reinventing checks per module::

    bearer token -> Principal -> AuthorizedFamilyContext -> capability

Status codes are established here once. 401 means "no usable identity". 404
means "not your family", and is also what a nonexistent family returns, so a
response can never confirm that a private family exists. 403 is reserved for a
member who lacks the capability -- by then membership is already established, so
saying so leaks nothing new.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from apps.api.errors import (
    AUTHENTICATION_REQUIRED,
    FAMILY_NOT_FOUND,
    INSUFFICIENT_FAMILY_ROLE,
    INVALID_TOKEN,
)
from mura.identity.context import (
    AuthorizedFamilyContext,
    FamilyAccessDenied,
    InsufficientFamilyRole,
)
from mura.identity.policy import Capability


def authentication_required() -> HTTPException:
    """No usable credential was presented at all."""

    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_REQUIRED)


def invalid_token() -> HTTPException:
    """A bearer token was presented and did not verify. Never says why."""

    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_TOKEN)


def family_not_found() -> HTTPException:
    """Used for both non-member and nonexistent family. Never distinguish them."""

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FAMILY_NOT_FOUND)


def insufficient_family_role() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=INSUFFICIENT_FAMILY_ROLE)


def build_family_context_dependency(
    *,
    principal_dependency: Callable[..., object],
    authorization_service_dependency: Callable[..., object],
) -> Callable[..., AuthorizedFamilyContext]:
    """Resolve membership once per request.

    FastAPI caches a dependency result within a request, so several capability
    guards on the same route share one membership query.
    """

    def resolve_family_context(
        family_id: str,
        principal: object = Depends(principal_dependency),
        service: object = Depends(authorization_service_dependency),
    ) -> AuthorizedFamilyContext:
        try:
            return service.authorize(principal, family_id)  # type: ignore[attr-defined]
        except FamilyAccessDenied as exc:
            raise family_not_found() from exc

    return resolve_family_context


def build_capability_dependency(
    capability: Capability,
    *,
    family_context_dependency: Callable[..., AuthorizedFamilyContext],
) -> Callable[..., AuthorizedFamilyContext]:
    """A route asks for a capability; it never inspects a role string."""

    def require_capability(
        context: AuthorizedFamilyContext = Depends(family_context_dependency),
    ) -> AuthorizedFamilyContext:
        try:
            context.require(capability)
        except InsufficientFamilyRole as exc:
            raise insufficient_family_role() from exc
        return context

    return require_capability


__all__ = [
    "AUTHENTICATION_REQUIRED",
    "FAMILY_NOT_FOUND",
    "INSUFFICIENT_FAMILY_ROLE",
    "INVALID_TOKEN",
    "authentication_required",
    "build_capability_dependency",
    "build_family_context_dependency",
    "family_not_found",
    "insufficient_family_role",
    "invalid_token",
]
