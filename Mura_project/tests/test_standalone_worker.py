from __future__ import annotations

import dataclasses
import signal
import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api.main import CoreRuntime, create_app, get_settings
from apps.worker.main import build_worker, install_signal_handlers, main
from mura.config import CoreSettings
from mura.orchestration import RecordingJobWorker

CORE_TOKEN = "c" * 40


def _settings(**overrides: Any) -> CoreSettings:
    payload: dict[str, Any] = {
        "DEEPSEEK_API_KEY": "sk-" + "d" * 40,
        "CORE_API_KEY": CORE_TOKEN,
        "WORKER_REGISTRATION_TOKEN": "r" * 40,
        "KAGGLE_ASR_API_KEY": "a" * 40,
        "OPERATIONS_API_KEY": "o" * 40,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "DATABASE_AUTO_CREATE": True,
    }
    payload.update(overrides)
    return CoreSettings.model_validate(payload)


# ------------------------------------------------------- API does not process


def test_api_runtime_has_no_worker() -> None:
    fields = {field.name for field in dataclasses.fields(CoreRuntime)}

    assert "worker" not in fields
    assert fields == {"settings", "database", "repository", "pipeline", "storage"}


def test_serving_requests_never_starts_job_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[str] = []
    monkeypatch.setattr(
        RecordingJobWorker,
        "start",
        lambda self: started.append("started"),
    )
    claimed: list[str] = []
    monkeypatch.setattr(
        RecordingJobWorker,
        "process_once",
        lambda self: claimed.append("claimed") or False,
    )
    settings = _settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(application, raise_server_exceptions=False)

    client.get("/health")
    client.get("/ready")
    client.get("/v1/capabilities", headers={"Authorization": f"Bearer {CORE_TOKEN}"})

    # The API must never claim a recording job just because it served traffic.
    assert started == []
    assert claimed == []


def test_health_and_ready_do_not_depend_on_a_worker() -> None:
    settings = _settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(application, raise_server_exceptions=False)

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


# ----------------------------------------------------------- worker lifecycle


def test_worker_is_constructed_with_lease_settings() -> None:
    worker = build_worker(_settings(JOB_LEASE_SECONDS=240, JOB_HEARTBEAT_SECONDS=60))

    assert worker.lease_seconds == 240
    assert worker.heartbeat_seconds == 60
    assert worker.worker_id.startswith("worker_")


def test_each_worker_process_gets_a_distinct_identity() -> None:
    first = build_worker(_settings())
    second = build_worker(_settings())

    assert first.worker_id != second.worker_id


def test_request_stop_ends_the_loop_without_touching_current_work() -> None:
    worker = build_worker(_settings())
    polled = threading.Event()

    def never_claims() -> bool:
        polled.set()
        return False

    worker.process_once = never_claims  # type: ignore[method-assign]
    thread = threading.Thread(target=worker.run_forever, daemon=True)
    thread.start()

    assert polled.wait(timeout=5)
    worker.request_stop()
    thread.join(timeout=5)

    assert not thread.is_alive()


def test_idle_polling_waits_instead_of_spinning() -> None:
    # 0.1s is the configured minimum poll interval.
    worker = build_worker(_settings(JOB_POLL_INTERVAL_SECONDS=0.1))
    calls: list[int] = []
    worker.process_once = lambda: calls.append(1) or False  # type: ignore[method-assign]
    thread = threading.Thread(target=worker.run_forever, daemon=True)

    thread.start()
    threading.Event().wait(0.4)
    worker.request_stop()
    thread.join(timeout=5)

    # With a 100ms interval a 400ms window allows only a handful of polls; a
    # spinning loop would produce thousands.
    assert len(calls) < 50


def test_signal_handlers_install_without_error() -> None:
    worker = build_worker(_settings())

    install_signal_handlers(worker)

    assert signal.getsignal(signal.SIGINT) is not None


def test_worker_refuses_to_start_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("DEEPSEEK_API_KEY", "CORE_API_KEY", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("apps.worker.main.CoreSettings", _raising_settings)

    assert main() == 2


class _raising_settings:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise ValueError("CORE_API_KEY too short: leaky-secret-value")
