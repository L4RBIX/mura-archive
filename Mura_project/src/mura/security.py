from __future__ import annotations

import hmac

from fastapi import HTTPException, status


def verify_bearer_token(authorization: str | None, *, expected_token: str) -> None:
    """Validate a bearer token without leaking token equality through early string comparison."""

    if not expected_token:
        raise RuntimeError("expected bearer token is not configured")

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )

    scheme, separator, supplied = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not supplied.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
        )

    if not hmac.compare_digest(supplied.strip(), expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
        )
