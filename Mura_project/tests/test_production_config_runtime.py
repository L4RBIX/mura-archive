from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import (
    REQUEST_ID_HEADER,
    create_app,
    get_settings,
    resolve_request_id,
)
from mura.config import CoreSettings, Environment
from mura.storage.database import Database, DatabaseRuntimeSettings, postgres_connect_args

DEEPSEEK_KEY = "sk-" + "d" * 40
REGISTRATION_TOKEN = "r" * 40
ASR_TOKEN = "a" * 40
CORE_TOKEN = "c" * 40

POSTGRES_URL = "postgresql+psycopg://mura:mura@db.internal:5432/mura"
SQLITE_MEMORY_URL = "sqlite+pysqlite:///:memory:"


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "DEEPSEEK_API_KEY": DEEPSEEK_KEY,
        "CORE_API_KEY": CORE_TOKEN,
        "WORKER_REGISTRATION_TOKEN": REGISTRATION_TOKEN,
        "KAGGLE_ASR_API_KEY": ASR_TOKEN,
        "OPERATIONS_API_KEY": "o" * 40,
        "DATABASE_URL": SQLITE_MEMORY_URL,
    }
    payload.update(overrides)
    return payload


def _production_payload(**overrides: Any) -> dict[str, Any]:
    payload = _payload(
        MURA_ENVIRONMENT="production",
        DATABASE_URL=POSTGRES_URL,
        CORS_ALLOWED_ORIGINS="https://app.example.com",
        # Production must not depend on a CWD-relative storage directory.
        AUDIO_STORAGE_DIR="/srv/mura/audio",
        # Production requires real OIDC; the disabled mode is local/test only.
        AUTH_MODE="oidc",
        AUTH_ISSUER="https://issuer.example.com/",
        AUTH_AUDIENCE="mura-core",
        AUTH_JWKS_URL="https://issuer.example.com/.well-known/jwks.json",
    )
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- settings


def test_database_auto_create_defaults_to_false() -> None:
    assert CoreSettings.model_validate(_payload()).database_auto_create is False


def test_local_environment_is_the_default() -> None:
    assert CoreSettings.model_validate(_payload()).environment is Environment.LOCAL


def test_local_may_still_use_sqlite_and_auto_create() -> None:
    settings = CoreSettings.model_validate(_payload(DATABASE_AUTO_CREATE="true"))

    assert settings.database_auto_create is True
    assert settings.database_url == SQLITE_MEMORY_URL


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_production_like_rejects_auto_create(environment: str) -> None:
    with pytest.raises(ValidationError, match="DATABASE_AUTO_CREATE"):
        CoreSettings.model_validate(
            _production_payload(MURA_ENVIRONMENT=environment, DATABASE_AUTO_CREATE="true")
        )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_production_like_rejects_sqlite(environment: str) -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        CoreSettings.model_validate(
            _production_payload(MURA_ENVIRONMENT=environment, DATABASE_URL=SQLITE_MEMORY_URL)
        )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_production_like_rejects_wildcard_cors(environment: str) -> None:
    with pytest.raises(ValidationError, match=r"\*"):
        CoreSettings.model_validate(
            _production_payload(MURA_ENVIRONMENT=environment, CORS_ALLOWED_ORIGINS="*")
        )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_production_like_requires_at_least_one_origin(environment: str) -> None:
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        CoreSettings.model_validate(
            _production_payload(MURA_ENVIRONMENT=environment, CORS_ALLOWED_ORIGINS="")
        )


@pytest.mark.parametrize(
    "origin",
    ["app.example.com", "https://app.example.com/path", "ftp://app.example.com", "https://"],
)
def test_malformed_origins_are_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        CoreSettings.model_validate(_production_payload(CORS_ALLOWED_ORIGINS=origin))


def test_valid_production_configuration_is_accepted() -> None:
    settings = CoreSettings.model_validate(
        _production_payload(CORS_ALLOWED_ORIGINS="https://app.example.com,https://www.example.com")
    )

    assert settings.environment is Environment.PRODUCTION
    assert settings.database_auto_create is False
    assert settings.cors_allowed_origins == [
        "https://app.example.com",
        "https://www.example.com",
    ]
    assert settings.api_docs_enabled is False


@pytest.mark.parametrize(
    ("environment", "expected"),
    [("local", True), ("test", True), ("staging", False), ("production", False)],
)
def test_docs_default_by_environment(environment: str, expected: bool) -> None:
    payload = (
        _payload(MURA_ENVIRONMENT=environment)
        if environment in {"local", "test"}
        else _production_payload(MURA_ENVIRONMENT=environment)
    )

    assert CoreSettings.model_validate(payload).api_docs_enabled is expected


def test_docs_can_be_explicitly_enabled_in_production() -> None:
    settings = CoreSettings.model_validate(_production_payload(EXPOSE_API_DOCS="true"))

    assert settings.api_docs_enabled is True


# --------------------------------------------------------------------------- database


def test_postgres_engine_applies_pool_settings() -> None:
    database = Database(
        POSTGRES_URL,
        runtime=DatabaseRuntimeSettings(pool_size=7, max_overflow=3, pool_recycle_seconds=900),
    )

    assert database.engine.pool.size() == 7
    assert database.engine.pool._max_overflow == 3
    assert database.engine.pool._recycle == 900


def test_postgres_connect_args_carry_timeouts() -> None:
    args = postgres_connect_args(
        DatabaseRuntimeSettings(connect_timeout_seconds=11, statement_timeout_seconds=17)
    )

    assert args["connect_timeout"] == 11
    assert args["options"] == "-c statement_timeout=17000"


def test_sqlite_memory_path_remains_compatible() -> None:
    database = Database(SQLITE_MEMORY_URL)
    database.create_schema()

    with database.session_factory() as session:
        assert session.get_bind() is database.engine


# --------------------------------------------------------------------------- request ids


def test_request_id_is_generated_when_absent() -> None:
    client = TestClient(create_app(CoreSettings.model_validate(_payload())))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER].startswith("req_")


def test_valid_incoming_request_id_is_reused() -> None:
    client = TestClient(create_app(CoreSettings.model_validate(_payload())))

    response = client.get("/health", headers={REQUEST_ID_HEADER: "trace-abc_123"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-abc_123"


@pytest.mark.parametrize(
    "supplied",
    ["short", "x" * 65, "has spaces", "semi;colon", "unicode-ә", ""],
)
def test_unsafe_incoming_request_ids_are_replaced(supplied: str) -> None:
    resolved = resolve_request_id(supplied)

    assert resolved != supplied
    assert resolved.startswith("req_")


# --------------------------------------------------------------------------- health/ready


def test_health_is_cheap_and_needs_no_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CORE_API_KEY", raising=False)
    client = TestClient(create_app(CoreSettings.model_validate(_payload())))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mura-core"}


def test_ready_succeeds_when_the_database_answers() -> None:
    settings = CoreSettings.model_validate(_payload())
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(application)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ready_fails_safely_when_the_database_is_unavailable(tmp_path: Path) -> None:
    unreachable = f"sqlite+pysqlite:///{tmp_path.as_posix()}/missing-directory/core.db"
    settings = CoreSettings.model_validate(_payload(DATABASE_URL=unreachable))
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(application)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert "missing-directory" not in response.text


# --------------------------------------------------------------------------- docs/CORS


def test_docs_are_served_locally() -> None:
    client = TestClient(create_app(CoreSettings.model_validate(_payload())))

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_are_disabled_in_production() -> None:
    client = TestClient(create_app(CoreSettings.model_validate(_production_payload())))

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_configured_origin_is_echoed_and_others_are_not() -> None:
    client = TestClient(create_app(CoreSettings.model_validate(_production_payload())))

    allowed = client.get("/health", headers={"Origin": "https://app.example.com"})
    denied = client.get("/health", headers={"Origin": "https://evil.example.com"})

    assert allowed.headers["access-control-allow-origin"] == "https://app.example.com"
    assert "access-control-allow-origin" not in denied.headers
    assert "access-control-allow-credentials" not in allowed.headers
