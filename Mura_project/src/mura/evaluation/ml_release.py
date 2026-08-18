from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from pydantic import Field

from mura.domain.models import StrictModel
from mura.evaluation.asr import (
    AsrEvaluationReport,
    AsrGateResult,
    evaluate_asr_gates,
    load_asr_dataset,
    load_asr_gate_config,
    run_asr_evaluation,
)
from mura.evaluation.e2e import (
    E2EGateResult,
    E2EReport,
    evaluate_e2e_gates,
    load_e2e_dataset,
    load_e2e_gate_config,
    run_e2e_evaluation,
)
from mura.evaluation.identity import (
    IdentityEvaluationReport,
    IdentityGateResult,
    evaluate_identity_gates,
    load_identity_gate_config,
    run_identity_evaluation,
)
from mura.evaluation.models import BenchmarkReport
from mura.evaluation.release_gates import (
    ReleaseGateResult,
    evaluate_release_gates,
    load_release_gate_config,
)
from mura.evaluation.runner import run_benchmark
from mura.versioning import get_pipeline_versions


class MLReleaseManifest(StrictModel):
    schema_version: str = "ml-release-manifest-v1"
    core_manifest: str
    core_release_gates: str
    coreference_dataset: str
    entity_resolution_dataset: str
    identity_release_gates: str
    asr_dataset: str
    asr_release_gates: str
    e2e_dataset: str
    e2e_release_gates: str


class MLReleaseReport(StrictModel):
    report_schema_version: str = "ml-release-report-v1"
    manifest_path: str
    source_commit: str
    pipeline_versions: dict[str, str]
    component_passed: dict[str, bool]
    component_report_sha256: dict[str, str]
    version_consistency: bool
    offline_release_candidate_passed: bool
    live_evaluation_required: bool = True
    failures: list[str] = Field(default_factory=list)
    core: BenchmarkReport
    core_gate: ReleaseGateResult
    identity: IdentityEvaluationReport
    identity_gate: IdentityGateResult
    asr: AsrEvaluationReport
    asr_gate: AsrGateResult
    e2e: E2EReport
    e2e_gate: E2EGateResult


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _digest_model(model: StrictModel) -> str:
    encoded = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_ml_release_manifest(path: Path) -> MLReleaseManifest:
    return MLReleaseManifest.model_validate_json(path.read_text(encoding="utf-8"))


def run_ml_release(manifest_path: Path) -> MLReleaseReport:
    resolved = manifest_path.resolve()
    manifest = load_ml_release_manifest(resolved)
    root = resolved.parent.parent.parent if resolved.parent.name == "release" else resolved.parent

    core = run_benchmark(_resolve(root, manifest.core_manifest))
    core_gate = evaluate_release_gates(
        core,
        load_release_gate_config(_resolve(root, manifest.core_release_gates)),
    )
    identity = run_identity_evaluation(
        coreference_path=_resolve(root, manifest.coreference_dataset),
        entity_path=_resolve(root, manifest.entity_resolution_dataset),
    )
    identity_gate = evaluate_identity_gates(
        identity,
        load_identity_gate_config(_resolve(root, manifest.identity_release_gates)),
    )
    asr = run_asr_evaluation(load_asr_dataset(_resolve(root, manifest.asr_dataset)))
    asr_gate = evaluate_asr_gates(
        asr,
        load_asr_gate_config(_resolve(root, manifest.asr_release_gates)),
    )
    e2e = run_e2e_evaluation(load_e2e_dataset(_resolve(root, manifest.e2e_dataset)))
    e2e_gate = evaluate_e2e_gates(
        e2e,
        load_e2e_gate_config(_resolve(root, manifest.e2e_release_gates)),
    )

    current_versions = get_pipeline_versions().model_dump(mode="json")
    version_consistency = (
        core.pipeline_versions == current_versions
        and identity.coreference.pipeline_versions == current_versions
        and identity.entity_resolution.pipeline_versions == current_versions
        and e2e.pipeline_versions == current_versions
        and all(current_versions.values())
    )
    component_passed = {
        "core": core_gate.passed,
        "identity": identity_gate.passed,
        "asr_contract": asr_gate.passed,
        "offline_e2e": e2e_gate.passed,
    }
    failures: list[str] = []
    for component, passed in component_passed.items():
        if not passed:
            failures.append(f"component gate failed: {component}")
    if not version_consistency:
        failures.append("pipeline version catalogs are inconsistent across component reports")
    report_hashes = {
        "core": _digest_model(core),
        "identity": _digest_model(identity),
        "asr_contract": _digest_model(asr),
        "offline_e2e": _digest_model(e2e),
    }
    return MLReleaseReport(
        manifest_path=resolved.as_posix(),
        source_commit=os.getenv("GITHUB_SHA") or "local-uncommitted-worktree",
        pipeline_versions=current_versions,
        component_passed=component_passed,
        component_report_sha256=report_hashes,
        version_consistency=version_consistency,
        offline_release_candidate_passed=not failures,
        failures=failures,
        core=core,
        core_gate=core_gate,
        identity=identity,
        identity_gate=identity_gate,
        asr=asr,
        asr_gate=asr_gate,
        e2e=e2e,
        e2e_gate=e2e_gate,
    )


def render_ml_release_report(report: MLReleaseReport) -> str:
    status = "PASS" if report.offline_release_candidate_passed else "FAIL"
    lines = [
        f"# Mura Offline ML Release Gate: {status}",
        "",
        "> Passing this report establishes an offline release candidate only. Live GigaAM + ",
        "> DeepSeek evaluation on approved audio remains mandatory before production promotion.",
        "",
        f"- Source commit: `{report.source_commit}`",
        f"- Version consistency: `{report.version_consistency}`",
        f"- Live evaluation required: `{report.live_evaluation_required}`",
        "",
        "## Component gates",
        "",
    ]
    for component, passed in sorted(report.component_passed.items()):
        lines.append(
            f"- {component}: **{'PASS' if passed else 'FAIL'}**, "
            f"report_sha256=`{report.component_report_sha256[component]}`"
        )
    if report.failures:
        lines.extend(["", "## Failures"])
        lines.extend(f"- {failure}" for failure in report.failures)
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The core, identity, and ASR component gates remain independently inspectable. "
            "The offline E2E component executes the real cleaner, focused extraction, "
            "sanitizer, provenance validation, coreference, and entity resolution paths with "
            "frozen external provider responses.",
        ]
    )
    return "\n".join(lines)


def write_ml_release_json(report: MLReleaseReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
