from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pydantic import Field, model_validator

from mura.coreference_boundaries import is_outside_quote, quote_scope_for_span
from mura.domain.models import (
    CoreferenceLink,
    CoreferenceStatus,
    EvidenceSpan,
    StrictModel,
    TranscriptEnvelope,
)
from mura.extraction_sanitizer import process_extraction_candidate
from mura.versioning import get_pipeline_versions


class GoldCoreferenceLink(StrictModel):
    anaphor_segment_id: str = Field(min_length=1)
    anaphor_text: str = Field(min_length=1)
    status: CoreferenceStatus
    antecedent_mention_ids: list[str] = Field(default_factory=list)
    candidate_mention_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> GoldCoreferenceLink:
        if self.status is CoreferenceStatus.RESOLVED and not self.antecedent_mention_ids:
            raise ValueError("gold resolved coreference requires antecedents")
        if self.status is not CoreferenceStatus.RESOLVED and self.antecedent_mention_ids:
            raise ValueError("only resolved gold coreference may contain antecedents")
        return self


class CoreferenceBenchmarkCase(StrictModel):
    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    construction_tags: list[str] = Field(default_factory=list)
    speaker_id: str = Field(min_length=1)
    speaker_name: str = Field(min_length=1)
    transcript: TranscriptEnvelope
    raw_extraction: dict
    gold_links: list[GoldCoreferenceLink] = Field(default_factory=list)
    forbidden_resolved_anaphors: list[str] = Field(default_factory=list)


class CoreferenceBenchmarkDataset(StrictModel):
    schema_version: str = "coreference-benchmark-v2"
    dataset_id: str = Field(min_length=1)
    description: str = ""
    cases: list[CoreferenceBenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> CoreferenceBenchmarkDataset:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("coreference benchmark case IDs must be unique")
        return self


class CoreferenceCaseScore(StrictModel):
    case_id: str
    gold_links: int = Field(ge=0)
    correct_status: int = Field(ge=0)
    correct_antecedents: int = Field(ge=0)
    resolved_gold: int = Field(ge=0)
    ambiguous_gold: int = Field(ge=0)
    correct_ambiguous_routing: int = Field(ge=0)
    unsupported_resolved_links: int = Field(ge=0)
    cross_quote_resolutions: int = Field(ge=0)
    forbidden_resolved_anaphors: int = Field(ge=0)
    predicted: list[CoreferenceLink] = Field(default_factory=list)


class CoreferenceBenchmarkSummary(StrictModel):
    case_count: int = Field(ge=0)
    gold_links: int = Field(ge=0)
    status_accuracy: float = Field(ge=0, le=1)
    antecedent_accuracy: float = Field(ge=0, le=1)
    ambiguous_routing_accuracy: float = Field(ge=0, le=1)
    unsupported_resolved_links: int = Field(ge=0)
    cross_quote_resolutions: int = Field(ge=0)
    forbidden_resolved_anaphors: int = Field(ge=0)


class CoreferenceBenchmarkReport(StrictModel):
    report_schema_version: str = "coreference-report-v2"
    dataset_id: str
    pipeline_versions: dict[str, str]
    cases: list[CoreferenceCaseScore]
    summary: CoreferenceBenchmarkSummary


def load_coreference_dataset(path: Path) -> CoreferenceBenchmarkDataset:
    return CoreferenceBenchmarkDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _anaphor_location(
    link: CoreferenceLink,
    *,
    evidence_by_id: Mapping[str, EvidenceSpan],
) -> tuple[str, str, int, int] | None:
    for evidence_id in link.evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            continue
        text = getattr(evidence, "text", None)
        segment_id = getattr(evidence, "segment_id", None)
        start = getattr(evidence, "start_char", None)
        end = getattr(evidence, "end_char", None)
        if text == link.anaphor_text and start is not None and end is not None:
            return str(segment_id), str(text), int(start), int(end)
    return None


def _score_case(case: CoreferenceBenchmarkCase) -> CoreferenceCaseScore:
    outcome = process_extraction_candidate(
        raw=case.raw_extraction,
        transcript=case.transcript,
        speaker_id=case.speaker_id,
        speaker_name=case.speaker_name,
    )
    predicted = outcome.result.coreference_links
    evidence_by_id = {item.evidence_id: item for item in outcome.result.evidence_spans}
    locations = {
        link.coreference_id: _anaphor_location(link, evidence_by_id=evidence_by_id)
        for link in predicted
    }

    matched_ids: set[str] = set()
    correct_status = 0
    correct_antecedents = 0
    resolved_gold = 0
    ambiguous_gold = 0
    correct_ambiguous = 0

    for gold in case.gold_links:
        matches = [
            link
            for link in predicted
            if (location := locations.get(link.coreference_id)) is not None
            and location[0] == gold.anaphor_segment_id
            and location[1].casefold() == gold.anaphor_text.casefold()
        ]
        if len(matches) != 1:
            resolved_gold += gold.status is CoreferenceStatus.RESOLVED
            ambiguous_gold += gold.status is CoreferenceStatus.AMBIGUOUS
            continue
        actual = matches[0]
        matched_ids.add(actual.coreference_id)
        correct_status += actual.status is gold.status
        if gold.status is CoreferenceStatus.RESOLVED:
            resolved_gold += 1
            correct_antecedents += sorted(actual.antecedent_mention_ids) == sorted(
                gold.antecedent_mention_ids
            )
        if gold.status is CoreferenceStatus.AMBIGUOUS:
            ambiguous_gold += 1
            correct_ambiguous += actual.status is CoreferenceStatus.AMBIGUOUS and sorted(
                actual.candidate_mention_ids
            ) == sorted(gold.candidate_mention_ids)

    unexpected_resolved = sum(
        link.status is CoreferenceStatus.RESOLVED and link.coreference_id not in matched_ids
        for link in predicted
    )
    forbidden = sum(
        link.status is CoreferenceStatus.RESOLVED
        and link.anaphor_text.casefold()
        in {surface.casefold() for surface in case.forbidden_resolved_anaphors}
        for link in predicted
    )
    segment_text = {segment.segment_id: segment.text for segment in case.transcript.segments}
    cross_quote = 0
    for link in predicted:
        if link.status is not CoreferenceStatus.RESOLVED:
            continue
        location = locations.get(link.coreference_id)
        if location is None:
            continue
        segment_id, _, start, end = location
        scope = quote_scope_for_span(segment_text[segment_id], start, end)
        cross_quote += not is_outside_quote(scope)

    return CoreferenceCaseScore(
        case_id=case.case_id,
        gold_links=len(case.gold_links),
        correct_status=correct_status,
        correct_antecedents=correct_antecedents,
        resolved_gold=resolved_gold,
        ambiguous_gold=ambiguous_gold,
        correct_ambiguous_routing=correct_ambiguous,
        unsupported_resolved_links=unexpected_resolved,
        cross_quote_resolutions=cross_quote,
        forbidden_resolved_anaphors=forbidden,
        predicted=predicted,
    )


def run_coreference_benchmark(path: Path) -> CoreferenceBenchmarkReport:
    dataset = load_coreference_dataset(path)
    cases = [_score_case(case) for case in dataset.cases]
    gold_links = sum(case.gold_links for case in cases)
    resolved_gold = sum(case.resolved_gold for case in cases)
    ambiguous_gold = sum(case.ambiguous_gold for case in cases)
    return CoreferenceBenchmarkReport(
        dataset_id=dataset.dataset_id,
        pipeline_versions=get_pipeline_versions().model_dump(mode="json"),
        cases=cases,
        summary=CoreferenceBenchmarkSummary(
            case_count=len(cases),
            gold_links=gold_links,
            status_accuracy=_safe_ratio(sum(case.correct_status for case in cases), gold_links),
            antecedent_accuracy=_safe_ratio(
                sum(case.correct_antecedents for case in cases), resolved_gold
            ),
            ambiguous_routing_accuracy=_safe_ratio(
                sum(case.correct_ambiguous_routing for case in cases), ambiguous_gold
            ),
            unsupported_resolved_links=sum(case.unsupported_resolved_links for case in cases),
            cross_quote_resolutions=sum(case.cross_quote_resolutions for case in cases),
            forbidden_resolved_anaphors=sum(case.forbidden_resolved_anaphors for case in cases),
        ),
    )
