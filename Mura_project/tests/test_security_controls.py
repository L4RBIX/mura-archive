from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import app, get_settings
from mura.config import CoreSettings, WorkerSettings
from mura.security import verify_bearer_token

DEEPSEEK_KEY = "sk-" + "d" * 40
REGISTRATION_TOKEN = "r" * 40
ASR_TOKEN = "a" * 40
CORE_TOKEN = "c" * 40


def core_settings() -> CoreSettings:
    return CoreSettings.model_validate(
        {
            "DEEPSEEK_API_KEY": DEEPSEEK_KEY,
            "CORE_API_KEY": CORE_TOKEN,
            "WORKER_REGISTRATION_TOKEN": REGISTRATION_TOKEN,
            "KAGGLE_ASR_API_KEY": ASR_TOKEN,
            "OPERATIONS_API_KEY": "o" * 40,
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            # Auto-create is opt-in since PR-02A; local/test workflows request it explicitly.
            "DATABASE_AUTO_CREATE": True,
        }
    )


def test_bearer_token_accepts_valid_value() -> None:
    verify_bearer_token(
        f"Bearer {ASR_TOKEN}",
        expected_token=ASR_TOKEN,
    )


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic abc", "Bearer", "Bearer wrong"],
)
def test_bearer_token_rejects_missing_or_invalid_value(
    authorization: str | None,
) -> None:
    with pytest.raises(HTTPException) as error:
        verify_bearer_token(authorization, expected_token=ASR_TOKEN)
    assert error.value.status_code == 401


def test_bearer_token_fails_closed_without_server_secret() -> None:
    with pytest.raises(RuntimeError, match="not configured"):
        verify_bearer_token(f"Bearer {ASR_TOKEN}", expected_token="")


def test_configuration_failure_never_echoes_the_supplied_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaked_secret = "too-short-but-secret-value"
    for name, value in {
        "MURA_ENVIRONMENT": "local",
        "DEEPSEEK_API_KEY": DEEPSEEK_KEY,
        "CORE_API_KEY": leaked_secret,
        "WORKER_REGISTRATION_TOKEN": REGISTRATION_TOKEN,
        "KAGGLE_ASR_API_KEY": ASR_TOKEN,
        "OPERATIONS_API_KEY": "o" * 40,
        "DATABASE_URL": "postgresql+psycopg://mura:hunter2@db.internal:5432/mura",
    }.items():
        monkeypatch.setenv(name, value)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/ready")

    assert response.status_code == 503
    assert leaked_secret not in response.text
    assert "hunter2" not in response.text
    # Canonical error envelope since API-CONTRACT-01A-i.
    assert response.json()["error"]["code"] == "service_unavailable"


def test_core_settings_require_strong_registration_token() -> None:
    with pytest.raises(ValidationError):
        CoreSettings.model_validate(
            {
                "DEEPSEEK_API_KEY": DEEPSEEK_KEY,
                "CORE_API_KEY": CORE_TOKEN,
                "WORKER_REGISTRATION_TOKEN": "short",
                "KAGGLE_ASR_API_KEY": ASR_TOKEN,
                "OPERATIONS_API_KEY": "o" * 40,
                "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            }
        )


def test_worker_callback_requires_registration_token() -> None:
    with pytest.raises(ValidationError, match="WORKER_REGISTRATION_TOKEN"):
        WorkerSettings.model_validate(
            {
                "KAGGLE_ASR_API_KEY": ASR_TOKEN,
                "OPERATIONS_API_KEY": "o" * 40,
                "CORE_BACKEND_URL": "https://mura.example.com",
                # Keep this test independent from a developer's local .env.
                "WORKER_REGISTRATION_TOKEN": None,
            }
        )


def test_worker_registration_requires_authentication_and_https() -> None:
    app.dependency_overrides[get_settings] = core_settings
    client = TestClient(app)
    try:
        unauthorized = client.post(
            "/v1/workers/register",
            json={"url": "https://worker.example.com"},
        )
        assert unauthorized.status_code == 401

        insecure = client.post(
            "/v1/workers/register",
            headers={"Authorization": f"Bearer {REGISTRATION_TOKEN}"},
            json={"url": "http://worker.example.com"},
        )
        assert insecure.status_code == 422

        accepted = client.post(
            "/v1/workers/register",
            headers={"Authorization": f"Bearer {REGISTRATION_TOKEN}"},
            json={"url": "https://worker.example.com/"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["url"] == "https://worker.example.com"

        hidden = client.get("/v1/workers/current")
        assert hidden.status_code == 401
    finally:
        app.dependency_overrides.clear()
