from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field, model_validator

from mura.domain.models import (
    ExtractionResult,
    MentionResolution,
    PersonMention,
    RelationshipClaim,
    ResolutionStatus,
    StrictModel,
)
from mura.entity_resolution import EntityResolutionContext, KnownPersonProfile
from mura.resolution import resolve_mentions_with_report
from mura.versioning import get_pipeline_versions


class GoldMentionResolution(StrictModel):
    mention_id: str = Field(min_length=1)
    status: ResolutionStatus
    person_id: str | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> GoldMentionResolution:
        if self.status is ResolutionStatus.RESOLVED and self.person_id is None:
            raise ValueError("gold resolved identity requires person_id")
        if self.status is not ResolutionStatus.RESOLVED and self.person_id is not None:
            raise ValueError("only gold resolved identity may contain person_id")
        return self


class EntityResolutionBenchmarkCase(StrictModel):
    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    construction_tags: list[str] = Field(default_factory=list)
    people_mentions: list[PersonMention] = Field(min_length=1)
    relationship_claims: list[RelationshipClaim] = Field(default_factory=list)
    profiles: list[KnownPersonProfile] = Field(default_factory=list)
    gold: list[GoldMentionResolution] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> EntityResolutionBenchmarkCase:
        mention_ids = [mention.mention_id for mention in self.people_mentions]
        gold_ids = [item.mention_id for item in self.gold]
        if len(mention_ids) != len(set(mention_ids)):
            raise ValueError("benchmark mention IDs must be unique")
        if sorted(mention_ids) != sorted(gold_ids):
            raise ValueError("benchmark gold must contain exactly one decision per mention")
        if any(profile.family_id != self.family_id for profile in self.profiles):
            raise ValueError("benchmark profiles must stay inside case family scope")
        return self


class EntityResolutionBenchmarkDataset(StrictModel):
    schema_version: str = "entity-resolution-benchmark-v2"
    dataset_id: str = Field(min_length=1)
    description: str = ""
    cases: list[EntityResolutionBenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> EntityResolutionBenchmarkDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("entity-resolution benchmark case IDs must be unique")
        return self


class EntityResolutionCaseScore(StrictModel):
    case_id: str
    mentions: int = Field(ge=0)
    correct_status: int = Field(ge=0)
    correct_identity: int = Field(ge=0)
    gold_resolved: int = Field(ge=0)
    false_merges: int = Field(ge=0)
    false_splits: int = Field(ge=0)
    correct_review_routing: int = Field(ge=0)
    gold_needs_review: int = Field(ge=0)
    correct_new_person: int = Field(ge=0)
    gold_new_person: int = Field(ge=0)
    predicted: list[MentionResolution] = Field(default_factory=list)
    verified_alias_collisions: int = Field(default=0, ge=0)
    mention_identity_collisions: int = Field(default=0, ge=0)
    inactive_relationships_ignored: int = Field(default=0, ge=0)


class EntityResolutionBenchmarkSummary(StrictModel):
    case_count: int = Field(ge=0)
    mentions: int = Field(ge=0)
    status_accuracy: float = Field(ge=0, le=1)
    identity_accuracy: float = Field(ge=0, le=1)
    review_routing_accuracy: float = Field(ge=0, le=1)
    new_person_accuracy: float = Field(ge=0, le=1)
    false_merges: int = Field(ge=0)
    false_splits: int = Field(ge=0)
    cross_family_merges: int = Field(default=0, ge=0)
    verified_alias_collisions: int = Field(default=0, ge=0)
    mention_identity_collisions: int = Field(default=0, ge=0)
    inactive_relationships_ignored: int = Field(default=0, ge=0)


class EntityResolutionBenchmarkReport(StrictModel):
    report_schema_version: str = "entity-resolution-report-v2"
    dataset_id: str
    pipeline_versions: dict[str, str]
    cases: list[EntityResolutionCaseScore]
    summary: EntityResolutionBenchmarkSummary


def load_entity_resolution_dataset(path: Path) -> EntityResolutionBenchmarkDataset:
    return EntityResolutionBenchmarkDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _extraction_for(case: EntityResolutionBenchmarkCase) -> ExtractionResult:
    return ExtractionResult(
        schema_version="extraction-v2",
        recording_id=f"recording_{case.case_id}",
        speaker_id="speaker_benchmark",
        speaker_name="Benchmark Speaker",
        languages=[],
        people_mentions=case.people_mentions,
        relationship_claims=case.relationship_claims,
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _score_case(case: EntityResolutionBenchmarkCase) -> EntityResolutionCaseScore:
    context = EntityResolutionContext(family_id=case.family_id, profiles=case.profiles)
    run = resolve_mentions_with_report(_extraction_for(case), context)
    predicted = run.resolutions
    predicted_by_id = {item.mention_id: item for item in predicted}

    correct_status = 0
    correct_identity = 0
    gold_resolved = 0
    false_merges = 0
    false_splits = 0
    correct_review_routing = 0
    gold_needs_review = 0
    correct_new_person = 0
    gold_new_person = 0

    for expected in case.gold:
        actual = predicted_by_id[expected.mention_id]
        correct_status += actual.status is expected.status
        if expected.status is ResolutionStatus.RESOLVED:
            gold_resolved += 1
            identity_matches = (
                actual.status is ResolutionStatus.RESOLVED
                and actual.person_id == expected.person_id
            )
            if identity_matches:
                correct_identity += 1
            else:
                false_splits += 1
        elif actual.status is ResolutionStatus.RESOLVED:
            false_merges += 1

        if expected.status is ResolutionStatus.NEEDS_REVIEW:
            gold_needs_review += 1
            correct_review_routing += actual.status is ResolutionStatus.NEEDS_REVIEW
        if expected.status is ResolutionStatus.NEW_PERSON:
            gold_new_person += 1
            correct_new_person += actual.status is ResolutionStatus.NEW_PERSON

    return EntityResolutionCaseScore(
        case_id=case.case_id,
        mentions=len(case.gold),
        correct_status=correct_status,
        correct_identity=correct_identity,
        gold_resolved=gold_resolved,
        false_merges=false_merges,
        false_splits=false_splits,
        correct_review_routing=correct_review_routing,
        gold_needs_review=gold_needs_review,
        correct_new_person=correct_new_person,
        gold_new_person=gold_new_person,
        predicted=predicted,
        verified_alias_collisions=run.metrics.verified_alias_collisions,
        mention_identity_collisions=run.metrics.mention_identity_collisions,
        inactive_relationships_ignored=run.metrics.inactive_relationships_ignored,
    )


def run_entity_resolution_benchmark(path: Path) -> EntityResolutionBenchmarkReport:
    dataset = load_entity_resolution_dataset(path)
    cases = [_score_case(case) for case in dataset.cases]
    mentions = sum(case.mentions for case in cases)
    correct_status = sum(case.correct_status for case in cases)
    gold_resolved = sum(case.gold_resolved for case in cases)
    correct_identity = sum(case.correct_identity for case in cases)
    gold_needs_review = sum(case.gold_needs_review for case in cases)
    correct_review = sum(case.correct_review_routing for case in cases)
    gold_new_person = sum(case.gold_new_person for case in cases)
    correct_new_person = sum(case.correct_new_person for case in cases)

    return EntityResolutionBenchmarkReport(
        dataset_id=dataset.dataset_id,
        pipeline_versions=get_pipeline_versions().model_dump(mode="json"),
        cases=cases,
        summary=EntityResolutionBenchmarkSummary(
            case_count=len(cases),
            mentions=mentions,
            status_accuracy=_safe_ratio(correct_status, mentions),
            identity_accuracy=_safe_ratio(correct_identity, gold_resolved),
            review_routing_accuracy=_safe_ratio(correct_review, gold_needs_review),
            new_person_accuracy=_safe_ratio(correct_new_person, gold_new_person),
            false_merges=sum(case.false_merges for case in cases),
            false_splits=sum(case.false_splits for case in cases),
            cross_family_merges=0,
            verified_alias_collisions=sum(case.verified_alias_collisions for case in cases),
            mention_identity_collisions=sum(case.mention_identity_collisions for case in cases),
            inactive_relationships_ignored=sum(
                case.inactive_relationships_ignored for case in cases
            ),
        ),
    )


def write_entity_resolution_report(path: Path, output: Path) -> None:
    report = run_entity_resolution_benchmark(path)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
