"""Every status the API can emit maps to an honest envelope code.

`_CODE_BY_STATUS` is a lookup with an `INTERNAL_ERROR` default, so a status
missing from it does not fail loudly -- it quietly claims the server broke.
That is how 405 came to answer `internal_error`: a caller using the wrong verb
was told the service had failed, and a genuine 500 became indistinguishable
from a routing mistake in logs and monitoring.

These tests pin the mapping itself rather than one route's behaviour, so the
next status added to the API has to be classified deliberately.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.errors import (
    _CODE_BY_STATUS,
    _MESSAGE_BY_CODE,
    _RETRYABLE_CODES,
    INTERNAL_ERROR,
    METHOD_NOT_ALLOWED,
)
from apps.api.main import create_app, get_settings
from mura.config import CoreSettings

CORE_TOKEN = "c" * 40


def _settings() -> CoreSettings:
    return CoreSettings.model_validate(
        {
            "DEEPSEEK_API_KEY": "d" * 40,
            "CORE_API_KEY": CORE_TOKEN,
            "WORKER_REGISTRATION_TOKEN": "w" * 40,
            "KAGGLE_ASR_API_KEY": "k" * 40,
            "OPERATIONS_API_KEY": "o" * 40,
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "DATABASE_AUTO_CREATE": True,
        }
    )


def _client() -> TestClient:
    settings = _settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    return TestClient(application, raise_server_exceptions=False)


def test_wrong_method_is_not_reported_as_a_server_fault() -> None:
    # /v1/process-transcript is POST-only. A GET is the caller's mistake.
    response = _client().get(
        "/v1/process-transcript",
        headers={"Authorization": f"Bearer {CORE_TOKEN}"},
    )
    assert response.status_code == 405
    body = response.json()["error"]
    assert body["code"] == METHOD_NOT_ALLOWED
    assert body["code"] != INTERNAL_ERROR
    # A wrong verb never succeeds on retry without the caller changing it.
    assert body["retryable"] is False


@pytest.mark.parametrize("status_code", sorted(_CODE_BY_STATUS))
def test_every_mapped_status_has_a_message(status_code: int) -> None:
    code = _CODE_BY_STATUS[status_code]
    assert code in _MESSAGE_BY_CODE, f"{status_code} maps to {code!r} with no message"
    assert _MESSAGE_BY_CODE[code].strip()


def test_only_500_maps_to_internal_error() -> None:
    """Any other status claiming `internal_error` is an unclassified status."""

    internal = {status for status, code in _CODE_BY_STATUS.items() if code == INTERNAL_ERROR}
    assert internal == {500}


def test_contract_errors_are_never_advertised_as_retryable() -> None:
    """A 4xx the caller must change is not retryable.

    429 is the deliberate exception: the request is well-formed and the same
    call succeeds once the window passes, which is exactly what retryable
    means here.
    """

    for status_code, code in _CODE_BY_STATUS.items():
        if 400 <= status_code < 500 and status_code != 429:
            assert code not in _RETRYABLE_CODES, f"{status_code} must not be retryable"


def test_error_messages_never_interpolate_request_content() -> None:
    """Messages are a fixed table; a format placeholder would invite leakage."""

    for message in _MESSAGE_BY_CODE.values():
        assert "{" not in message and "%" not in message
