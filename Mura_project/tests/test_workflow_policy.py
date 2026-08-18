from __future__ import annotations

import json
from pathlib import Path

from scripts.ci.check_workflow_policy import validate_workflow_policy


def test_repository_workflows_follow_policy() -> None:
    assert validate_workflow_policy() == []


def test_policy_rejects_mutable_action_and_dangerous_trigger(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "unsafe.yml").write_text(
        """name: Unsafe
on:
  pull_request_target:
permissions: write-all
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: true
      - run: echo unsafe
        continue-on-error: true
""",
        encoding="utf-8",
    )
    pins = tmp_path / "pins.json"
    pins.write_text(
        json.dumps(
            {
                "actions": {
                    "actions/checkout": {
                        "sha": "a" * 40,
                        "tag": "v-test",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    errors = validate_workflow_policy(workflows, pins)

    assert any("pull_request_target" in error for error in errors)
    assert any("write-all" in error for error in errors)
    assert any("continue-on-error" in error for error in errors)
    assert any("mutable" in error for error in errors)
    assert any("persist-credentials" in error for error in errors)
