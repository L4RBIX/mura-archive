from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mura.identity.auth import (
    AuthenticationError,
    AuthMode,
    OidcAuthVerifier,
    bearer_credentials,
    validate_jwks_url,
)

ISSUER = "https://issuer.test/"
AUDIENCE = "mura-core"
KID = "test-key-1"


# A keypair generated inside the test run. No production key is ever committed.
@pytest.fixture(scope="module")
def keypair() -> tuple[Any, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private, pem.decode()


class _FakeSigningKey:
    def __init__(self, key: Any) -> None:
        self.key = key


class _FakeJwkClient:
    """Stands in for PyJWKClient so no network call is ever made."""

    def __init__(self, public_key: Any, *, kid: str = KID, fail: bool = False) -> None:
        self._public_key = public_key
        self._kid = kid
        self._fail = fail
        self.calls = 0

    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        self.calls += 1
        if self._fail:
            raise RuntimeError("jwks unavailable")
        header = jwt.get_unverified_header(token)
        if header.get("kid") != self._kid:
            raise RuntimeError("unknown key id")
        return _FakeSigningKey(self._public_key)


def _verifier(keypair: tuple[Any, str], **overrides: Any) -> OidcAuthVerifier:
    private, _ = keypair
    client = overrides.pop("jwk_client", _FakeJwkClient(private.public_key()))
    return OidcAuthVerifier(
        issuer=overrides.pop("issuer", ISSUER),
        audience=overrides.pop("audience", AUDIENCE),
        jwks_url="https://issuer.test/.well-known/jwks.json",
        jwk_client=client,
        **overrides,
    )


def _token(keypair: tuple[Any, str], /, **claims: Any) -> str:
    private, _ = keypair
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "provider-subject-1",
        "exp": now + 300,
        "iat": now,
    }
    payload.update(claims)
    headers = {"kid": claims.pop("_kid", KID)}
    return jwt.encode(payload, private, algorithm="RS256", headers=headers)


# ------------------------------------------------------------------ accepted


def test_valid_rs256_token_yields_a_verified_identity(keypair: tuple[Any, str]) -> None:
    identity = _verifier(keypair).verify(f"Bearer {_token(keypair, email='a@b.test')}")

    assert identity.issuer == ISSUER
    assert identity.subject == "provider-subject-1"
    assert identity.email == "a@b.test"


def test_nbf_in_the_past_is_accepted(keypair: tuple[Any, str]) -> None:
    token = _token(keypair, nbf=int(time.time()) - 60)

    assert _verifier(keypair).verify(f"Bearer {token}").subject


# ------------------------------------------------------------------ rejected


def test_missing_credentials_are_rejected(keypair: tuple[Any, str]) -> None:
    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(None)


@pytest.mark.parametrize("header", ["", "Token abc", "Bearer", "Bearer    ", "basic abc"])
def test_malformed_authorization_headers_are_rejected(header: str) -> None:
    with pytest.raises(AuthenticationError):
        bearer_credentials(header)


def test_bad_signature_is_rejected(keypair: tuple[Any, str]) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "attacker",
            "exp": int(time.time()) + 300,
        },
        other,
        algorithm="RS256",
        headers={"kid": KID},
    )

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {forged}")


def test_expired_token_is_rejected(keypair: tuple[Any, str]) -> None:
    token = _token(keypair, exp=int(time.time()) - 600)

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {token}")


def test_future_nbf_is_rejected(keypair: tuple[Any, str]) -> None:
    token = _token(keypair, nbf=int(time.time()) + 3600)

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {token}")


def test_wrong_issuer_is_rejected(keypair: tuple[Any, str]) -> None:
    token = _token(keypair, iss="https://evil.test/")

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {token}")


def test_wrong_audience_is_rejected(keypair: tuple[Any, str]) -> None:
    token = _token(keypair, aud="some-other-api")

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {token}")


def test_missing_exp_is_rejected(keypair: tuple[Any, str]) -> None:
    private, _ = keypair
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "s"},
        private,
        algorithm="RS256",
        headers={"kid": KID},
    )

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {token}")


@pytest.mark.parametrize("subject", [None, "", "   "])
def test_missing_or_empty_subject_is_rejected(
    keypair: tuple[Any, str], subject: str | None
) -> None:
    token = _token(keypair, sub=subject)

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {token}")


def test_unknown_kid_is_rejected(keypair: tuple[Any, str]) -> None:
    private, _ = keypair
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "s", "exp": int(time.time()) + 300},
        private,
        algorithm="RS256",
        headers={"kid": "rotated-away"},
    )

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {token}")


def test_alg_none_is_rejected(keypair: tuple[Any, str]) -> None:
    unsigned = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "s", "exp": int(time.time()) + 300},
        key="",
        algorithm="none",
    )

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {unsigned}")


def test_hs256_token_cannot_impersonate_via_key_confusion(
    keypair: tuple[Any, str],
) -> None:
    # The classic confusion attack signs with the public key as an HMAC secret.
    # PyJWT refuses to encode that, so this uses a plain HMAC token instead: the
    # property under test is that the RS256-only allowlist never accepts HS256,
    # whatever secret was used.
    forged = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "admin", "exp": int(time.time()) + 300},
        "attacker-chosen-secret",
        algorithm="HS256",
        headers={"kid": KID},
    )

    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify(f"Bearer {forged}")


def test_garbage_token_is_rejected(keypair: tuple[Any, str]) -> None:
    with pytest.raises(AuthenticationError):
        _verifier(keypair).verify("Bearer not-a-jwt")


def test_jwks_retrieval_failure_is_an_authentication_error(
    keypair: tuple[Any, str],
) -> None:
    private, _ = keypair
    verifier = _verifier(keypair, jwk_client=_FakeJwkClient(private.public_key(), fail=True))

    with pytest.raises(AuthenticationError):
        verifier.verify(f"Bearer {_token(keypair)}")


def test_failures_do_not_disclose_the_reason(keypair: tuple[Any, str]) -> None:
    token = _token(keypair, iss="https://evil.test/")

    with pytest.raises(AuthenticationError) as error:
        _verifier(keypair).verify(f"Bearer {token}")

    # A bad signature and a wrong issuer must look identical to a caller.
    assert str(error.value) == "token could not be verified"


# ---------------------------------------------------------------- jwks trust


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://issuer.test/jwks", "data:application/json,{}", "notaurl"],
)
def test_untrusted_jwks_schemes_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        validate_jwks_url(url, require_https=False)


def test_https_is_required_outside_local_development() -> None:
    with pytest.raises(ValueError):
        validate_jwks_url("http://issuer.test/jwks", require_https=True)
    assert validate_jwks_url("http://localhost:8080/jwks", require_https=False)


def test_auth_mode_enum_has_no_debug_bypass() -> None:
    assert {mode.value for mode in AuthMode} == {"disabled", "oidc"}
