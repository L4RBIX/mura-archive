"""Provider-neutral authentication boundary.

Everything above this module works with a verified ``Principal``. PyJWT appears
only here, so swapping identity providers -- or the verification library -- never
reaches the domain.

Two rules shape the design. Nothing is trusted before the signature verifies, so
claims are never read from an unverified token. And the JWKS endpoint comes only
from server configuration: a token can never influence where keys are fetched
from, which is what keeps a forged ``iss`` from turning into SSRF.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlparse

import jwt
from jwt import PyJWKClient

#: Asymmetric only, decided server-side. The token's own `alg` never widens this.
#: HS* is deliberately excluded: mixing symmetric and public-key verification is
#: how key-confusion attacks happen. RS256 is the OIDC baseline every provider
#: supports, so it is the whole allowlist until a provider requires more.
DEFAULT_ALLOWED_ALGORITHMS = ("RS256",)

_ALLOWED_JWKS_SCHEMES = frozenset({"https", "http"})


class AuthMode(StrEnum):
    """How principals are established.

    ``disabled`` exists for local development and tests only; production-like
    environments reject it in configuration, and there is deliberately no debug
    header that could authenticate a request by accident.
    """

    DISABLED = "disabled"
    OIDC = "oidc"


class AuthenticationError(Exception):
    """Token missing, malformed, or failed verification.

    Carries no detail about *why*: an unknown key and a bad signature are the
    same answer to a caller, and distinguishing them helps only an attacker.
    """


@dataclass(frozen=True)
class VerifiedIdentity:
    """What the provider asserts, after the signature verified."""

    issuer: str
    subject: str
    email: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class Principal:
    """A verified identity resolved to an internal MURA user.

    ``user_id`` is MURA's own identifier, never the provider subject. The raw
    token is deliberately absent: it is verified once and never carried further.
    """

    user_id: str
    issuer: str
    subject: str
    email: str | None = None
    display_name: str | None = None


class ApplicationAuthVerifier(Protocol):
    def verify(self, credentials: str | None) -> VerifiedIdentity: ...


def validate_jwks_url(url: str, *, require_https: bool) -> str:
    """The JWKS endpoint is trusted configuration, so validate it as such."""

    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_JWKS_SCHEMES or not parsed.netloc:
        raise ValueError("AUTH_JWKS_URL must be an http(s) URL")
    if require_https and parsed.scheme != "https":
        raise ValueError("AUTH_JWKS_URL must use HTTPS outside local development")
    return url


def bearer_credentials(authorization: str | None) -> str:
    scheme, separator, token = (authorization or "").partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("missing bearer token")
    return token.strip()


class OidcAuthVerifier:
    """Standards-compliant JWT verification against a configured JWKS endpoint."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        allowed_algorithms: tuple[str, ...] = DEFAULT_ALLOWED_ALGORITHMS,
        clock_skew_seconds: int = 30,
        jwks_cache_seconds: int = 300,
        jwk_client: Any | None = None,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.allowed_algorithms = tuple(allowed_algorithms)
        self.clock_skew_seconds = clock_skew_seconds
        # The client is built from configuration only. Injection exists for
        # tests; it is never derived from a request or a token.
        self._jwk_client = jwk_client or PyJWKClient(
            jwks_url,
            cache_keys=True,
            lifespan=jwks_cache_seconds,
        )

    def verify(self, credentials: str | None) -> VerifiedIdentity:
        token = bearer_credentials(credentials) if credentials else ""
        if not token:
            raise AuthenticationError("missing bearer token")
        try:
            # Selects the key by `kid` from the configured endpoint only.
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self.allowed_algorithms),
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.clock_skew_seconds,
                options={
                    "require": ["exp", "iss", "aud", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except Exception as exc:
            # Deliberately uniform: signature, expiry, issuer, audience and
            # unknown-key failures are indistinguishable to the caller.
            raise AuthenticationError("token could not be verified") from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationError("token subject is missing")
        issuer = claims.get("iss")
        if not isinstance(issuer, str) or not issuer:
            raise AuthenticationError("token issuer is missing")

        email = claims.get("email")
        name = claims.get("name") or claims.get("preferred_username")
        return VerifiedIdentity(
            issuer=issuer,
            subject=subject.strip(),
            # Email is profile metadata, never identity.
            email=email if isinstance(email, str) and email else None,
            display_name=name if isinstance(name, str) and name else None,
        )


class StaticAuthVerifier:
    """Test/local verifier. Configuration forbids it in production-like modes."""

    def __init__(self, identity: VerifiedIdentity) -> None:
        self._identity = identity

    def verify(self, credentials: str | None) -> VerifiedIdentity:
        if not credentials:
            raise AuthenticationError("missing bearer token")
        return self._identity
