from __future__ import annotations

import json
from pathlib import Path

import pytest

from mura.release_control import (
    CURRENT_RELEASE_ID,
    PREVIOUS_RELEASE_ID,
    ReleaseControlService,
    evaluate_runtime_budget,
)
from mura.replay import FamilyReplayService, ReplayNotFoundError
from mura.retention import RetentionConfirmationError, RetentionService
from mura.smoke import _synthetic_result, run_smoke
from mura.storage.database import Database


def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'release.db'}")
    database.create_schema()
    return database


def test_runtime_budget_passes_fixture_and_reports_breach() -> None:
    result = _synthetic_result()
    passing = evaluate_runtime_budget(result)
    assert passing.passed is True
    assert passing.complete is True
    assert passing.measurements["weighted_cost_units"] == 500

    slow_result = result.model_copy(
        update={"processing": {**result.processing, "total_seconds": 181.0}}
    )
    failing = evaluate_runtime_budget(slow_result)
    assert failing.passed is False
    assert failing.failures == ["pipeline_seconds=181.0 exceeds maximum 180.0"]


def test_release_control_rollback_is_audited_and_requires_restart(tmp_path: Path) -> None:
    service = ReleaseControlService(_database(tmp_path))
    initial = service.get_state()
    assert initial.active_release_id == CURRENT_RELEASE_ID
    assert initial.previous_release_id == PREVIOUS_RELEASE_ID
    assert initial.runtime_matches_desired is True

    rollback = service.rollback(requested_by="test-suite", note="test rollback")
    assert rollback.state.active_release_id == PREVIOUS_RELEASE_ID
    assert rollback.state.previous_release_id == CURRENT_RELEASE_ID
    assert rollback.state.restart_required is True

    restored = service.activate(
        release_id=CURRENT_RELEASE_ID,
        requested_by="test-suite",
        note="restore current runtime",
    )
    assert restored.state.active_release_id == CURRENT_RELEASE_ID
    assert restored.state.runtime_matches_desired is True
    assert restored.state.generation == 3


def test_replay_rejects_family_without_completed_results(tmp_path: Path) -> None:
    service = FamilyReplayService(_database(tmp_path))
    with pytest.raises(ReplayNotFoundError, match="no completed recordings"):
        service.run(family_id="missing-family")


def test_retention_requires_exact_confirmation(tmp_path: Path) -> None:
    service = RetentionService(_database(tmp_path))
    preview = service.preview()
    assert preview.applied is False
    assert "pipeline_results" in preview.preserved_data
    with pytest.raises(RetentionConfirmationError, match="confirmation must equal"):
        service.apply(confirmation="yes")


def test_release_manifest_matches_runtime_catalog() -> None:
    payload = json.loads(Path("release/mura-core-v1.0.0-rc1.json").read_text(encoding="utf-8"))
    assert payload["release_id"] == CURRENT_RELEASE_ID
    assert payload["budgets"]["maximum_weighted_cost_units"] == 240_000
    assert payload["verification"]["local_smoke_command"] == "mura-release-smoke"


def test_one_command_release_smoke_passes(tmp_path: Path) -> None:
    report = run_smoke(tmp_path / "smoke.db")
    assert report["passed"] is True, report
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert all(checks.values())
