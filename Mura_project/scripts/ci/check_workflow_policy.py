#!/usr/bin/env python3
"""Fail CI when workflow changes weaken GitHub Actions security controls."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"
PINS_PATH = REPOSITORY_ROOT / ".github" / "action-pins.json"

USES_PATTERN = re.compile(r"^\s*(?:-\s+)?uses:\s*['\"]?(?P<reference>[^'\"\s#]+)")
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_SNIPPETS = {
    "pull_request_target:": "pull_request_target executes untrusted PR code with base privileges",
    "permissions: write-all": "workflows may not request write-all permissions",
    "continue-on-error: true": "continue-on-error: true may not hide security or quality failures",
}


def _workflow_paths(directory: Path) -> list[Path]:
    return sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])


def _action_repository(reference: str) -> str:
    path, _, _ = reference.partition("@")
    return "/".join(path.split("/")[:2])


def load_action_pins(path: Path = PINS_PATH) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("actions")
    if not isinstance(entries, dict):
        raise ValueError("action-pins.json must contain an actions object")

    result: dict[str, str] = {}
    for repository, metadata in entries.items():
        if not isinstance(metadata, dict):
            raise ValueError(f"pin metadata for {repository} must be an object")
        sha = metadata.get("sha")
        tag = metadata.get("tag")
        if not isinstance(sha, str) or not FULL_SHA_PATTERN.fullmatch(sha):
            raise ValueError(f"pin for {repository} must be a lowercase 40-character SHA")
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError(f"pin for {repository} must include a readable release tag")
        result[repository] = sha
    return result


def validate_workflow_policy(
    workflows_directory: Path = WORKFLOWS_DIRECTORY,
    pins_path: Path = PINS_PATH,
) -> list[str]:
    errors: list[str] = []
    try:
        pins = load_action_pins(pins_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot load action pin registry: {exc}"]

    workflow_paths = _workflow_paths(workflows_directory)
    if not workflow_paths:
        return ["no GitHub Actions workflows were found"]

    for workflow_path in workflow_paths:
        text = workflow_path.read_text(encoding="utf-8")
        lowered = text.lower()
        location = workflow_path.name

        for snippet, explanation in FORBIDDEN_SNIPPETS.items():
            if snippet in lowered:
                errors.append(f"{location}: {explanation}")

        if "permissions:" not in lowered or "contents: read" not in lowered:
            errors.append(f"{location}: declare least-privilege permissions with contents: read")
        if "timeout-minutes:" not in lowered:
            errors.append(f"{location}: every workflow must bound job runtime with timeout-minutes")

        checkout_used = False
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = USES_PATTERN.match(line)
            if not match:
                continue
            reference = match.group("reference")
            if reference.startswith(("./", "../")):
                continue
            if "@" not in reference:
                errors.append(f"{location}:{line_number}: action reference has no immutable SHA")
                continue

            _, _, ref = reference.partition("@")
            repository = _action_repository(reference)
            if repository == "actions/checkout":
                checkout_used = True
            if not FULL_SHA_PATTERN.fullmatch(ref):
                errors.append(
                    f"{location}:{line_number}: {reference} is mutable; pin a full commit SHA"
                )
                continue
            expected = pins.get(repository)
            if expected is None:
                errors.append(
                    f"{location}:{line_number}: {repository} is missing from action-pins.json"
                )
            elif expected != ref:
                errors.append(
                    f"{location}:{line_number}: {repository} uses {ref}, expected {expected}"
                )

        if checkout_used and "persist-credentials: false" not in lowered:
            errors.append(f"{location}: checkout must set persist-credentials: false")

    return errors


def main() -> int:
    errors = validate_workflow_policy()
    if errors:
        print("Workflow policy failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Workflow policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
