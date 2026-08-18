from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import create_app, get_settings
from mura.config import CoreSettings

CORE_TOKEN = "c" * 40
OPERATIONS_TOKEN = "o" * 40
WORKER_TOKEN = "r" * 40

OPERATOR_ROUTES = [
    ("get", "/v1/operations/release"),
    ("post", "/v1/operations/release/activate"),
    ("post", "/v1/operations/release/rollback"),
    ("get", "/v1/operations/retention"),
    ("post", "/v1/operations/retention/apply"),
]


def _settings(**overrides: Any) -> CoreSettings:
    payload: dict[str, Any] = {
        "DEEPSEEK_API_KEY": "sk-" + "d" * 40,
        "CORE_API_KEY": CORE_TOKEN,
        "OPERATIONS_API_KEY": OPERATIONS_TOKEN,
        "WORKER_REGISTRATION_TOKEN": WORKER_TOKEN,
        "KAGGLE_ASR_API_KEY": "a" * 40,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "DATABASE_AUTO_CREATE": True,
    }
    payload.update(overrides)
    return CoreSettings.model_validate(payload)


def _client() -> TestClient:
    settings = _settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    return TestClient(application, raise_server_exceptions=False)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(("method", "path"), OPERATOR_ROUTES)
def test_core_token_cannot_reach_operator_routes(method: str, path: str) -> None:
    response = getattr(_client(), method)(path, headers=_auth(CORE_TOKEN))

    # This is the P0: a leaked application token must not activate a release
    # or apply retention.
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(("method", "path"), OPERATOR_ROUTES)
def test_operator_routes_accept_the_operations_token(method: str, path: str) -> None:
    response = getattr(_client(), method)(path, headers=_auth(OPERATIONS_TOKEN))

    assert response.status_code != 401


@pytest.mark.parametrize(("method", "path"), OPERATOR_ROUTES)
def test_operator_routes_reject_a_missing_token(method: str, path: str) -> None:
    assert getattr(_client(), method)(path).status_code == 401


def test_operator_routes_reject_the_worker_token() -> None:
    response = _client().get("/v1/operations/release", headers=_auth(WORKER_TOKEN))

    assert response.status_code == 401


def test_error_never_reveals_which_credential_was_expected() -> None:
    body = _client().get("/v1/operations/release", headers=_auth(CORE_TOKEN)).text

    for secret in (CORE_TOKEN, OPERATIONS_TOKEN, WORKER_TOKEN):
        assert secret not in body
    assert "operations_api_key" not in body.lower()


@pytest.mark.parametrize("token", [CORE_TOKEN, OPERATIONS_TOKEN, WORKER_TOKEN])
def test_no_machine_credential_reaches_the_user_application(token: str) -> None:
    """Since PR-03B-SWITCH the application surface is users only.

    /v1/capabilities is the unscoped user route, so it is the cheapest place to
    prove that none of the three machine credentials is a master key for product
    data -- family-scoped proof lives in the credential matrix suite.
    """

    assert _client().get("/v1/capabilities", headers=_auth(token)).status_code == 401


def test_job_trace_remains_on_the_application_token() -> None:
    response = _client().get("/v1/jobs/job_missing/trace", headers=_auth(CORE_TOKEN))

    # Read-only diagnostics stay with the application credential; 404 proves the
    # request authenticated and simply found nothing.
    assert response.status_code == 404


def test_production_rejects_reusing_the_core_token_for_operations() -> None:
    with pytest.raises(ValidationError, match="OPERATIONS_API_KEY"):
        _settings(
            MURA_ENVIRONMENT="production",
            OPERATIONS_API_KEY=CORE_TOKEN,
            DATABASE_URL="postgresql+psycopg://mura:mura@db.internal:5432/mura",
            CORS_ALLOWED_ORIGINS="https://app.example.com",
            AUDIO_STORAGE_DIR="/srv/mura/audio",
            DATABASE_AUTO_CREATE=False,
            AUTH_MODE="oidc",
            AUTH_ISSUER="https://issuer.example.com/",
            AUTH_AUDIENCE="mura-core",
            AUTH_JWKS_URL="https://issuer.example.com/.well-known/jwks.json",
        )


def test_operations_key_must_meet_the_secret_strength_standard() -> None:
    with pytest.raises(ValidationError):
        _settings(OPERATIONS_API_KEY="short")
