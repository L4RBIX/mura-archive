from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from mura.domain.models import StrictModel
from services.kaggle_asr.artifacts import (
    GIGAAM_MODEL_COMMIT,
    GIGAAM_MODEL_ID,
    GIGAAM_MODEL_VARIANT,
    SILERO_VAD_VERSION,
)
from services.kaggle_asr.chunking import (
    CHUNKER_VERSION,
    ChunkRecord,
    TranscriptPart,
    merge_transcript_parts_with_diagnostics,
)

_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_RUNTIME_METADATA = (
    "model_id",
    "model_variant",
    "model_commit",
    "chunker_version",
    "vad_version",
)


class AsrChunk(StrictModel):
    index: int = Field(ge=1)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str

    @model_validator(mode="after")
    def validate_range(self) -> AsrChunk:
        if self.end <= self.start:
            raise ValueError("chunk end must be greater than start")
        return self


class AsrEvaluationCase(StrictModel):
    case_id: str = Field(min_length=1)
    language: Literal["ru", "kk", "mixed"]
    reference: str = Field(min_length=1)
    hypothesis: str
    chunks: list[AsrChunk] = Field(default_factory=list)
    expected_merged_text: str | None = None
    required_repeat_phrases: list[str] = Field(default_factory=list)
    expected_duplicate_words_removed: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_chunk_expectations(self) -> AsrEvaluationCase:
        if not any(char.isalnum() for char in self.reference):
            raise ValueError("ASR reference must contain at least one letter or digit")
        if self.chunks and self.expected_merged_text is None:
            raise ValueError("chunk cases require expected_merged_text")
        return self


class AsrEvaluationDataset(StrictModel):
    schema_version: str = "asr-evaluation-dataset-v1"
    dataset_id: str = Field(min_length=1)
    source_type: Literal["synthetic", "public_licensed", "approved_private"]
    license_or_consent: str = Field(min_length=1)
    description: str = ""
    runtime_metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    cases: list[AsrEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> AsrEvaluationDataset:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("ASR evaluation case IDs must be unique")
        return self


class EditMetric(StrictModel):
    reference_units: int = Field(ge=0)
    substitutions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    insertions: int = Field(ge=0)
    error_rate: float = Field(ge=0)


class AsrCaseReport(StrictModel):
    case_id: str
    language: str
    word: EditMetric
    character: EditMetric
    merged_text: str | None = None
    boundary_merge_correct: bool | None = None
    repeat_phrases_preserved: int = Field(ge=0)
    repeat_phrases_total: int = Field(ge=0)
    duplicate_words_removed: int = Field(ge=0)
    duplicate_removal_expected: int | None = Field(default=None, ge=0)


class AsrLanguageReport(StrictModel):
    language: str
    case_count: int = Field(ge=0)
    word: EditMetric
    character: EditMetric


class AsrEvaluationReport(StrictModel):
    report_schema_version: str = "asr-evaluation-report-v1"
    dataset_id: str
    source_type: str
    license_or_consent: str
    runtime_metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    case_count: int = Field(ge=1)
    word: EditMetric
    character: EditMetric
    languages: list[AsrLanguageReport]
    boundary_cases: int = Field(ge=0)
    boundary_merge_correct: int = Field(ge=0)
    repeat_phrases_preserved: int = Field(ge=0)
    repeat_phrases_total: int = Field(ge=0)
    duplicate_removal_expectations_met: int = Field(ge=0)
    duplicate_removal_expectations_total: int = Field(ge=0)
    cases: list[AsrCaseReport]


class AsrGateConfig(StrictModel):
    schema_version: str = "asr-release-gates-v1"
    minimum_case_count: int = Field(ge=1)
    minimum_language_case_count: dict[str, int]
    maximum_word_error_rate: float = Field(ge=0)
    maximum_character_error_rate: float = Field(ge=0)
    minimum_boundary_merge_accuracy: float = Field(ge=0, le=1)
    minimum_repeat_preservation: float = Field(ge=0, le=1)
    minimum_duplicate_expectation_accuracy: float = Field(ge=0, le=1)


class AsrGateResult(StrictModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _Counts:
    reference: int
    substitutions: int
    deletions: int
    insertions: int

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions


def normalize_asr_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = "".join(char if char.isalnum() or char.isspace() else " " for char in normalized)
    return " ".join(normalized.split())


def _edit_counts(reference: list[str], hypothesis: list[str]) -> _Counts:
    # Each cell stores (distance, substitutions, deletions, insertions). The tie order is
    # deterministic: match/substitution, deletion, insertion.
    previous: list[tuple[int, int, int, int]] = [(j, 0, 0, j) for j in range(len(hypothesis) + 1)]
    for i, ref in enumerate(reference, start=1):
        current: list[tuple[int, int, int, int]] = [(i, 0, i, 0)]
        for j, hyp in enumerate(hypothesis, start=1):
            diagonal = previous[j - 1]
            if ref == hyp:
                candidates = [diagonal]
            else:
                candidates = [(diagonal[0] + 1, diagonal[1] + 1, diagonal[2], diagonal[3])]
            deletion = previous[j]
            insertion = current[j - 1]
            candidates.append((deletion[0] + 1, deletion[1], deletion[2] + 1, deletion[3]))
            candidates.append((insertion[0] + 1, insertion[1], insertion[2], insertion[3] + 1))
            current.append(
                min(candidates, key=lambda value: (value[0], value[1], value[2], value[3]))
            )
        previous = current
    _, substitutions, deletions, insertions = previous[-1]
    return _Counts(len(reference), substitutions, deletions, insertions)


def _metric(counts: _Counts) -> EditMetric:
    denominator = counts.reference or 1
    return EditMetric(
        reference_units=counts.reference,
        substitutions=counts.substitutions,
        deletions=counts.deletions,
        insertions=counts.insertions,
        error_rate=counts.errors / denominator,
    )


def _sum_counts(values: list[_Counts]) -> _Counts:
    return _Counts(
        reference=sum(value.reference for value in values),
        substitutions=sum(value.substitutions for value in values),
        deletions=sum(value.deletions for value in values),
        insertions=sum(value.insertions for value in values),
    )


def load_asr_dataset(path: Path) -> AsrEvaluationDataset:
    return AsrEvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def load_asr_gate_config(path: Path) -> AsrGateConfig:
    return AsrGateConfig.model_validate_json(path.read_text(encoding="utf-8"))


def run_asr_evaluation(dataset: AsrEvaluationDataset) -> AsrEvaluationReport:
    case_reports: list[AsrCaseReport] = []
    word_counts: list[_Counts] = []
    character_counts: list[_Counts] = []
    per_language_words: dict[str, list[_Counts]] = {}
    per_language_chars: dict[str, list[_Counts]] = {}
    boundary_cases = boundary_correct = 0
    repeats_preserved = repeats_total = 0
    duplicate_met = duplicate_total = 0

    for case in dataset.cases:
        reference_normalized = normalize_asr_text(case.reference)
        hypothesis_normalized = normalize_asr_text(case.hypothesis)
        words = _edit_counts(reference_normalized.split(), hypothesis_normalized.split())
        characters = _edit_counts(
            list(reference_normalized.replace(" ", "")),
            list(hypothesis_normalized.replace(" ", "")),
        )
        word_counts.append(words)
        character_counts.append(characters)
        per_language_words.setdefault(case.language, []).append(words)
        per_language_chars.setdefault(case.language, []).append(characters)

        merged_text: str | None = None
        boundary_ok: bool | None = None
        duplicate_removed = 0
        if case.chunks:
            parts = [
                TranscriptPart(
                    chunk=ChunkRecord(
                        index=chunk.index,
                        path=Path(f"fixture-{chunk.index}.wav"),
                        start=chunk.start,
                        end=chunk.end,
                    ),
                    text=chunk.text,
                )
                for chunk in case.chunks
            ]
            merged_text, diagnostics = merge_transcript_parts_with_diagnostics(parts)
            boundary_cases += 1
            boundary_ok = normalize_asr_text(merged_text) == normalize_asr_text(
                case.expected_merged_text or ""
            )
            boundary_correct += int(boundary_ok)
            duplicate_removed = diagnostics.duplicate_words_removed
            if case.expected_duplicate_words_removed is not None:
                duplicate_total += 1
                duplicate_met += int(duplicate_removed == case.expected_duplicate_words_removed)

        case_repeats_preserved = 0
        repeat_source = normalize_asr_text(
            merged_text if merged_text is not None else case.hypothesis
        )
        for phrase in case.required_repeat_phrases:
            repeats_total += 1
            phrase_normalized = normalize_asr_text(phrase)
            if phrase_normalized and phrase_normalized in repeat_source:
                repeats_preserved += 1
                case_repeats_preserved += 1

        case_reports.append(
            AsrCaseReport(
                case_id=case.case_id,
                language=case.language,
                word=_metric(words),
                character=_metric(characters),
                merged_text=merged_text,
                boundary_merge_correct=boundary_ok,
                repeat_phrases_preserved=case_repeats_preserved,
                repeat_phrases_total=len(case.required_repeat_phrases),
                duplicate_words_removed=duplicate_removed,
                duplicate_removal_expected=case.expected_duplicate_words_removed,
            )
        )

    language_reports = [
        AsrLanguageReport(
            language=language,
            case_count=len(per_language_words[language]),
            word=_metric(_sum_counts(per_language_words[language])),
            character=_metric(_sum_counts(per_language_chars[language])),
        )
        for language in sorted(per_language_words)
    ]
    return AsrEvaluationReport(
        dataset_id=dataset.dataset_id,
        source_type=dataset.source_type,
        license_or_consent=dataset.license_or_consent,
        runtime_metadata=dataset.runtime_metadata,
        case_count=len(dataset.cases),
        word=_metric(_sum_counts(word_counts)),
        character=_metric(_sum_counts(character_counts)),
        languages=language_reports,
        boundary_cases=boundary_cases,
        boundary_merge_correct=boundary_correct,
        repeat_phrases_preserved=repeats_preserved,
        repeat_phrases_total=repeats_total,
        duplicate_removal_expectations_met=duplicate_met,
        duplicate_removal_expectations_total=duplicate_total,
        cases=case_reports,
    )


def evaluate_asr_gates(report: AsrEvaluationReport, config: AsrGateConfig) -> AsrGateResult:
    failures: list[str] = []
    if report.case_count < config.minimum_case_count:
        failures.append(f"case count {report.case_count} < {config.minimum_case_count}")
    by_language = {item.language: item.case_count for item in report.languages}
    for language, minimum in config.minimum_language_case_count.items():
        if by_language.get(language, 0) < minimum:
            failures.append(
                f"language {language} case count {by_language.get(language, 0)} < {minimum}"
            )
    if report.word.error_rate > config.maximum_word_error_rate:
        failures.append(f"WER {report.word.error_rate:.4f} > {config.maximum_word_error_rate:.4f}")
    if report.character.error_rate > config.maximum_character_error_rate:
        failures.append(
            f"CER {report.character.error_rate:.4f} > {config.maximum_character_error_rate:.4f}"
        )
    boundary_accuracy = report.boundary_merge_correct / (report.boundary_cases or 1)
    if boundary_accuracy < config.minimum_boundary_merge_accuracy:
        failures.append(
            f"boundary accuracy {boundary_accuracy:.4f} < "
            f"{config.minimum_boundary_merge_accuracy:.4f}"
        )
    repeat_accuracy = report.repeat_phrases_preserved / (report.repeat_phrases_total or 1)
    if repeat_accuracy < config.minimum_repeat_preservation:
        failures.append(
            f"repeat preservation {repeat_accuracy:.4f} < {config.minimum_repeat_preservation:.4f}"
        )
    duplicate_accuracy = report.duplicate_removal_expectations_met / (
        report.duplicate_removal_expectations_total or 1
    )
    if duplicate_accuracy < config.minimum_duplicate_expectation_accuracy:
        failures.append(
            f"duplicate expectation accuracy {duplicate_accuracy:.4f} < "
            f"{config.minimum_duplicate_expectation_accuracy:.4f}"
        )
    return AsrGateResult(passed=not failures, failures=failures)


def validate_runtime_metadata(
    metadata: dict[str, str | int | float | bool],
) -> list[str]:
    """Return fail-closed validation failures for a live ASR evaluation manifest."""
    failures = [key for key in _REQUIRED_RUNTIME_METADATA if not metadata.get(key)]
    messages = [f"runtime metadata missing required field: {key}" for key in failures]

    commit = metadata.get("model_commit")
    if commit and (not isinstance(commit, str) or not _COMMIT_SHA_PATTERN.fullmatch(commit)):
        messages.append("runtime metadata model_commit must be an immutable 40-character SHA")

    expected_identity = {
        "model_id": GIGAAM_MODEL_ID,
        "model_variant": GIGAAM_MODEL_VARIANT,
        "model_commit": GIGAAM_MODEL_COMMIT,
        "chunker_version": CHUNKER_VERSION,
        "vad_version": SILERO_VAD_VERSION,
    }
    for key, expected in expected_identity.items():
        value = metadata.get(key)
        if value and value != expected:
            messages.append(f"runtime metadata {key} does not match the release manifest")

    artifact_hashes = {
        key: value for key, value in metadata.items() if key.startswith("artifact_sha256:")
    }
    if not artifact_hashes:
        messages.append("runtime metadata must include at least one artifact SHA-256")
    for key, value in artifact_hashes.items():
        if not isinstance(value, str) or not _ARTIFACT_SHA_PATTERN.fullmatch(value):
            messages.append(f"runtime metadata contains an invalid artifact digest: {key}")
    return messages


def render_asr_report(report: AsrEvaluationReport, gate: AsrGateResult) -> str:
    boundary_accuracy = report.boundary_merge_correct / (report.boundary_cases or 1)
    repeat_accuracy = report.repeat_phrases_preserved / (report.repeat_phrases_total or 1)
    duplicate_accuracy = report.duplicate_removal_expectations_met / (
        report.duplicate_removal_expectations_total or 1
    )
    lines = [
        "# Mura ASR Evaluation",
        "",
        f"- Dataset: `{report.dataset_id}`",
        f"- Source type: `{report.source_type}`",
        f"- License/consent: {report.license_or_consent}",
        f"- Cases: **{report.case_count}**",
        f"- WER: **{report.word.error_rate:.4f}**",
        f"- CER: **{report.character.error_rate:.4f}**",
        f"- Boundary merge accuracy: **{boundary_accuracy:.4f}**",
        f"- Repeat preservation: **{repeat_accuracy:.4f}**",
        f"- Duplicate expectation accuracy: **{duplicate_accuracy:.4f}**",
        "",
        "## Runtime metadata",
        "",
    ]
    if report.runtime_metadata:
        lines.extend(
            f"- `{key}`: `{value}`" for key, value in sorted(report.runtime_metadata.items())
        )
    else:
        lines.append("- Not provided (offline frozen-hypothesis contract dataset).")
    lines.extend(
        [
            "",
            "## Languages",
            "",
            "| Language | Cases | WER | CER |",
            "|---|---:|---:|---:|",
        ]
    )
    lines.extend(
        f"| {item.language} | {item.case_count} | {item.word.error_rate:.4f} | "
        f"{item.character.error_rate:.4f} |"
        for item in report.languages
    )
    lines.extend(["", "## Gate", "", f"**{'PASS' if gate.passed else 'FAIL'}**"])
    if gate.failures:
        lines.extend(f"- {failure}" for failure in gate.failures)
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This offline report validates normalization, WER/CER accounting and chunk-boundary "
            "merge behavior against frozen hypotheses. It is not a claim about live GigaAM "
            "accuracy on real family recordings. Live GPU evaluation must use approved audio "
            "fixtures and record the exact model commit and artifact hashes.",
        ]
    )
    return "\n".join(lines)


def write_asr_json(report: AsrEvaluationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
