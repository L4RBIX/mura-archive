from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mura.evaluation.models import (
    BenchmarkDataset,
    BenchmarkManifest,
    BenchmarkReport,
    CaseEvaluation,
)
from mura.evaluation.scoring import aggregate_case_metrics, score_case
from mura.extraction_sanitizer import process_extraction_candidate
from mura.versioning import get_pipeline_versions


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def load_manifest(path: str | Path) -> BenchmarkManifest:
    return BenchmarkManifest.model_validate(_read_json(Path(path)))


def load_dataset(path: str | Path) -> BenchmarkDataset:
    return BenchmarkDataset.model_validate(_read_json(Path(path)))


def _resolve_dataset_path(manifest_path: Path, dataset_path: str) -> Path:
    candidate = Path(dataset_path)
    if candidate.is_absolute():
        return candidate
    return manifest_path.parent / candidate


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def run_benchmark(manifest_path: str | Path) -> BenchmarkReport:
    resolved_manifest_path = Path(manifest_path).resolve()
    manifest = load_manifest(resolved_manifest_path)
    evaluations: list[CaseEvaluation] = []

    for entry in manifest.datasets:
        if not entry.enabled:
            continue
        dataset_path = _resolve_dataset_path(resolved_manifest_path, entry.path)
        dataset = load_dataset(dataset_path)
        if dataset.dataset_id != entry.dataset_id:
            raise ValueError(
                f"manifest dataset_id={entry.dataset_id!r} does not match "
                f"dataset_id={dataset.dataset_id!r} in {dataset_path}"
            )

        for case in dataset.cases:
            outcome = process_extraction_candidate(
                raw=case.raw_extraction,
                transcript=case.transcript,
                speaker_id=case.speaker_id,
                speaker_name=case.speaker_name,
            )
            evaluations.append(
                score_case(
                    case=case,
                    dataset_id=dataset.dataset_id,
                    split=entry.split,
                    extraction=outcome.result,
                    issues=outcome.issues,
                    evidence_closure_relationships=outcome.evidence_closure_count,
                    evidence_recovery=outcome.evidence_recovery,
                )
            )

    if not evaluations:
        raise ValueError("benchmark manifest contains no enabled cases")

    return BenchmarkReport(
        report_schema_version="evaluation-report-v4",
        manifest_path=_display_path(resolved_manifest_path),
        pipeline_versions=get_pipeline_versions().model_dump(mode="json"),
        cases=evaluations,
        summary=aggregate_case_metrics(evaluations),
    )
