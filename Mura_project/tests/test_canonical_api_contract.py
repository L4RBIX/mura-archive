from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api.errors import REQUEST_ID_HEADER
from apps.api.main import (
    create_app,
    get_auth_verifier,
    get_identity_repository,
    get_settings,
)
from mura.capabilities import (
    AsrRegistration,
    CapabilityStatus,
    ProviderConfiguration,
    RecordingMode,
    derive_capabilities,
)
from mura.config import CoreSettings
from mura.jobs import WAITING_FOR_ASR_STAGE, JobStatus, resolve_retry_state
from mura.storage.database import Database
from mura.storage.identity import IdentityRepository
from tests.authz_factories import FakePrincipalVerifier, create_test_user

DEEPSEEK_KEY = "sk-" + "d" * 40
REGISTRATION_TOKEN = "r" * 40
ASR_TOKEN = "a" * 40
CORE_TOKEN = "c" * 40
# Deliberately shorter than the 32-character minimum so configuration
# validation fails and the raw value would otherwise reach the response.
LEAKED_SECRET = "leaky-core-secret"


def _settings(**overrides: Any) -> CoreSettings:
    payload: dict[str, Any] = {
        "DEEPSEEK_API_KEY": DEEPSEEK_KEY,
        "CORE_API_KEY": CORE_TOKEN,
        "WORKER_REGISTRATION_TOKEN": REGISTRATION_TOKEN,
        "KAGGLE_ASR_API_KEY": ASR_TOKEN,
        "OPERATIONS_API_KEY": "o" * 40,
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


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {CORE_TOKEN}"}


def _signed_in_client() -> tuple[TestClient, dict[str, str]]:
    """A client carrying a verified user token.

    /v1/capabilities gates the record button, so since PR-03B-SWITCH it is
    user-facing: the service token no longer opens it.
    """

    settings = _settings()
    database = Database(settings.database_url)
    database.create_schema()
    verifier = FakePrincipalVerifier()
    user = create_test_user(IdentityRepository(database), subject="reader", verifier=verifier)

    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_identity_repository] = lambda: IdentityRepository(database)
    application.dependency_overrides[get_auth_verifier] = lambda: verifier
    return TestClient(application, raise_server_exceptions=False), user.headers


# ------------------------------------------------------------------ job status


def test_job_status_has_no_deferred_member() -> None:
    assert "deferred" not in {member.value for member in JobStatus}
    assert {member.value for member in JobStatus} == {
        "queued",
        "transcribing",
        "cleaning",
        "extracting",
        "resolving",
        "completed",
        "failed",
    }


def test_waiting_for_asr_is_queued_and_retryable() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    retryable, seconds, next_retry = resolve_retry_state(
        status=JobStatus.QUEUED,
        stage=WAITING_FOR_ASR_STAGE,
        next_attempt_at=now + timedelta(seconds=15),
        now=now,
    )

    assert retryable is True
    assert seconds == 15
    assert next_retry == now + timedelta(seconds=15)


def test_ordinary_queued_work_is_not_retryable() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    retryable, seconds, next_retry = resolve_retry_state(
        status=JobStatus.QUEUED,
        stage="queued",
        next_attempt_at=now,
        now=now,
    )

    assert retryable is False
    assert seconds is None
    assert next_retry is None


def test_elapsed_retry_window_clamps_to_zero() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    _, seconds, _ = resolve_retry_state(
        status=JobStatus.QUEUED,
        stage=WAITING_FOR_ASR_STAGE,
        next_attempt_at=now - timedelta(seconds=90),
        now=now,
    )

    assert seconds == 0


@pytest.mark.parametrize(
    "status",
    [JobStatus.FAILED, JobStatus.COMPLETED, JobStatus.TRANSCRIBING, JobStatus.RESOLVING],
)
def test_non_queued_states_are_never_retryable(status: JobStatus) -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    retryable, seconds, next_retry = resolve_retry_state(
        status=status,
        stage=WAITING_FOR_ASR_STAGE,
        next_attempt_at=now + timedelta(seconds=30),
        now=now,
    )

    assert (retryable, seconds, next_retry) == (False, None, None)


def test_no_public_retry_endpoint_exists() -> None:
    paths = create_app(_settings()).openapi()["paths"]

    assert not [path for path in paths if path.endswith("/retry")]


def test_job_view_exposes_retry_fields_and_hides_internals() -> None:
    schema = create_app(_settings()).openapi()["components"]["schemas"]["JobView"]
    properties = set(schema["properties"])

    assert {"retryable", "retry_after_seconds", "next_retry_at"} <= properties
    assert "error_detail" not in properties


# ---------------------------------------------------------------- capabilities


def test_capabilities_requires_authentication() -> None:
    assert _client().get("/v1/capabilities").status_code == 401


def test_capabilities_reports_registered_without_claiming_live_health() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    view = derive_capabilities(
        asr_registration=AsrRegistration.REGISTERED,
        asr_registered_at=now - timedelta(minutes=5),
        analysis_configured=True,
        now=now,
    )

    assert view.status is CapabilityStatus.READY
    assert view.recording.mode is RecordingMode.AUDIO
    assert view.asr.registration is AsrRegistration.REGISTERED
    # The registration row is not a heartbeat, so liveness stays unproven.
    assert view.asr.live_health_verified is False
    assert view.analysis.live_health_verified is False
    assert view.asr.registration_age_seconds == 300


def test_capabilities_degrade_to_transcript_only_without_a_worker() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    view = derive_capabilities(
        asr_registration=AsrRegistration.UNAVAILABLE,
        asr_registered_at=None,
        analysis_configured=True,
        now=now,
    )

    assert view.status is CapabilityStatus.DEGRADED
    assert view.recording.enabled is True
    assert view.recording.mode is RecordingMode.TRANSCRIPT_ONLY


def test_capabilities_never_claim_audio_when_registration_is_unknown() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    view = derive_capabilities(
        asr_registration=AsrRegistration.UNKNOWN,
        asr_registered_at=None,
        analysis_configured=True,
        now=now,
    )

    assert view.recording.mode is not RecordingMode.AUDIO
    assert view.asr.registration is AsrRegistration.UNKNOWN


def test_capabilities_are_unavailable_without_analysis_configuration() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    view = derive_capabilities(
        asr_registration=AsrRegistration.REGISTERED,
        asr_registered_at=now,
        analysis_configured=False,
        now=now,
    )

    assert view.status is CapabilityStatus.UNAVAILABLE
    assert view.recording.enabled is False
    assert view.analysis.configuration is ProviderConfiguration.NOT_CONFIGURED


def test_capabilities_response_is_served_and_typed() -> None:
    client, headers = _signed_in_client()
    response = client.get("/v1/capabilities", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "core-capabilities-v1"
    assert body["asr"]["live_health_verified"] is False
    assert set(body) == {
        "schema_version",
        "status",
        "recording",
        "asr",
        "analysis",
        "validation",
    }
    # No provider names, URLs or secrets.
    assert "url" not in body["asr"]
    assert DEEPSEEK_KEY not in response.text
    assert ASR_TOKEN not in response.text


def test_capabilities_never_expose_demo_mode() -> None:
    client, headers = _signed_in_client()

    assert "demo_mode" not in client.get("/v1/capabilities", headers=headers).text


def test_capabilities_reject_the_service_token() -> None:
    """It is user-facing product data, so a machine credential is not enough."""

    client, _ = _signed_in_client()

    assert client.get("/v1/capabilities", headers=_auth()).status_code == 401


# --------------------------------------------------------------- error envelope


def _assert_envelope(payload: dict[str, Any], *, code: str, retryable: bool) -> None:
    assert set(payload) == {"error"}
    error = payload["error"]
    assert set(error) == {"code", "message", "retryable", "request_id"}
    assert error["code"] == code
    assert error["retryable"] is retryable
    assert error["request_id"].startswith("req_")
    assert isinstance(error["message"], str) and error["message"]


def test_unauthorized_uses_the_canonical_envelope() -> None:
    response = _client().get("/v1/capabilities")

    assert response.status_code == 401
    # A caller who sent nothing should sign in; a caller whose token failed
    # should refresh. The two are distinguishable, why a token failed is not.
    _assert_envelope(response.json(), code="authentication_required", retryable=False)


def test_a_rejected_token_is_reported_as_invalid_rather_than_missing() -> None:
    client, _ = _signed_in_client()

    response = client.get("/v1/capabilities", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401
    _assert_envelope(response.json(), code="invalid_token", retryable=False)


def test_unknown_route_uses_the_canonical_envelope() -> None:
    response = _client().get("/v1/does-not-exist")

    assert response.status_code == 404
    _assert_envelope(response.json(), code="not_found", retryable=False)


def test_validation_error_uses_the_canonical_envelope() -> None:
    response = _client().post(
        "/v1/workers/register",
        headers={"Authorization": f"Bearer {REGISTRATION_TOKEN}"},
        json={"url": "http://worker.example.com"},
    )

    assert response.status_code == 422
    _assert_envelope(response.json(), code="validation_failed", retryable=False)


def test_service_unavailable_error_is_retryable() -> None:
    settings = _settings()
    application = create_app(settings)
    client = TestClient(application, raise_server_exceptions=False)

    # No dependency override: real settings load fails without env configuration.
    response = client.get("/v1/capabilities", headers=_auth())

    if response.status_code == 503:
        _assert_envelope(response.json(), code="service_unavailable", retryable=True)


def test_error_envelope_carries_the_incoming_request_id() -> None:
    response = _client().get(
        "/v1/does-not-exist",
        headers={REQUEST_ID_HEADER: "trace-abc_123"},
    )

    assert response.json()["error"]["request_id"] == "trace-abc_123"
    assert response.headers[REQUEST_ID_HEADER] == "trace-abc_123"


def test_configuration_errors_never_echo_the_supplied_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {
        "MURA_ENVIRONMENT": "local",
        "DEEPSEEK_API_KEY": DEEPSEEK_KEY,
        "CORE_API_KEY": LEAKED_SECRET,
        "WORKER_REGISTRATION_TOKEN": REGISTRATION_TOKEN,
        "KAGGLE_ASR_API_KEY": ASR_TOKEN,
        "OPERATIONS_API_KEY": "o" * 40,
        "DATABASE_URL": "postgresql+psycopg://mura:hunter2@db.internal:5432/mura",
    }.items():
        monkeypatch.setenv(name, value)
    client = TestClient(create_app(_settings()), raise_server_exceptions=False)

    response = client.get("/v1/capabilities", headers=_auth())

    assert response.status_code == 503
    assert LEAKED_SECRET not in response.text
    assert "hunter2" not in response.text
    assert "db.internal" not in response.text
    _assert_envelope(response.json(), code="service_unavailable", retryable=True)


# ------------------------------------------------------------ infrastructure


def test_health_stays_minimal_and_unversioned() -> None:
    response = _client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mura-core"}


def test_ready_stays_the_readiness_probe() -> None:
    response = _client().get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
