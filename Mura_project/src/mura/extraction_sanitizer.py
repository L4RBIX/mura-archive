from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from mura.claim_model import close_extraction_conflicts, materialize_extraction_contract_v2
from mura.claim_semantics import add_temporal_conflicts, harden_claim_semantics
from mura.domain.models import (
    CleanerResult,
    ConflictSet,
    CoreferenceLink,
    EvidenceSpan,
    ExtractionResult,
    FamilyEvent,
    PersonDescription,
    PersonMention,
    ProvenanceActivity,
    RelationshipClaim,
    Story,
    StorySensitivity,
    TranscriptEnvelope,
    UnresolvedQuestion,
    VerificationStatus,
)
from mura.evidence import complete_relationship_evidence
from mura.evidence_recovery import EvidenceOffsetRecoveryMetrics, recover_evidence_offsets
from mura.extraction_issues import (
    ExtractionIssue,
    ExtractionIssueCode,
    IssueSeverity,
    IssueStage,
)
from mura.factual_support import sensitivity_level
from mura.validation import ContractValidationError, validate_extraction_result

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class ExtractionSanitizationOutcome:
    recovered_raw: dict[str, Any]
    result: ExtractionResult
    issues: list[dict[str, Any]]
    evidence_closure_count: int
    evidence_recovery: EvidenceOffsetRecoveryMetrics


def _issue(
    issues: list[ExtractionIssue],
    *,
    object_type: str,
    object_id: str | None,
    stage: IssueStage,
    code: ExtractionIssueCode,
    severity: IssueSeverity = IssueSeverity.ERROR,
    recoverable: bool = False,
    related_ids: list[str] | None = None,
) -> None:
    issues.append(
        ExtractionIssue.create(
            stage=stage,
            object_type=object_type,
            object_id=object_id,
            code=code,
            severity=severity,
            recoverable=recoverable,
            related_ids=related_ids,
        )
    )


def _object_id(raw: object, field_name: str) -> str | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get(field_name)
    return value if isinstance(value, str) and value else None


def _list_value(raw: dict[str, Any], key: str, issues: list[ExtractionIssue]) -> list[object]:
    value = raw.get(key, [])
    if isinstance(value, list):
        return value
    _issue(
        issues,
        object_type=key,
        object_id=None,
        stage=IssueStage.SCHEMA,
        code=ExtractionIssueCode.TOP_LEVEL_NOT_LIST,
        severity=IssueSeverity.FATAL,
    )
    return []


def _force_unreviewed(
    raw_item: object,
    *,
    object_type: str,
    id_field: str,
    issues: list[ExtractionIssue],
) -> object:
    if not isinstance(raw_item, dict):
        return raw_item
    updated = dict(raw_item)
    status = updated.get("verification_status")
    if status is not None and status != VerificationStatus.UNREVIEWED.value:
        _issue(
            issues,
            object_type=object_type,
            object_id=_object_id(updated, id_field),
            stage=IssueStage.PROVENANCE,
            code=ExtractionIssueCode.VERIFICATION_STATUS_DOWNGRADED,
            severity=IssueSeverity.WARNING,
            recoverable=True,
        )
        updated["verification_status"] = VerificationStatus.UNREVIEWED.value
    if object_type == "story" and updated.get("privacy") not in (None, "private"):
        _issue(
            issues,
            object_type=object_type,
            object_id=_object_id(updated, id_field),
            stage=IssueStage.PRIVACY,
            code=ExtractionIssueCode.STORY_PRIVACY_FORCED_PRIVATE,
            severity=IssueSeverity.WARNING,
            recoverable=True,
        )
        updated["privacy"] = "private"
    return updated


def _parse_items(
    *,
    raw_items: list[object],
    model_type: type[ModelT],
    object_type: str,
    id_field: str,
    issues: list[ExtractionIssue],
    quarantined_ids: frozenset[str] = frozenset(),
) -> list[ModelT]:
    parsed: list[ModelT] = []
    seen_ids: set[str] = set()

    for candidate in raw_items:
        raw_item = _force_unreviewed(
            candidate,
            object_type=object_type,
            id_field=id_field,
            issues=issues,
        )
        object_id = _object_id(raw_item, id_field)
        if object_id is not None and object_id in quarantined_ids:
            continue
        try:
            item = model_type.model_validate(raw_item)
        except ValidationError:
            _issue(
                issues,
                object_type=object_type,
                object_id=object_id,
                stage=IssueStage.SCHEMA,
                code=ExtractionIssueCode.OBJECT_SCHEMA_INVALID,
            )
            continue

        resolved_id = str(getattr(item, id_field))
        if resolved_id in seen_ids:
            _issue(
                issues,
                object_type=object_type,
                object_id=resolved_id,
                stage=IssueStage.SCHEMA,
                code=ExtractionIssueCode.DUPLICATE_OBJECT_ID,
            )
            continue
        seen_ids.add(resolved_id)
        parsed.append(item)

    return parsed


def _base_result(
    *,
    recording_id: str,
    speaker_id: str,
    speaker_name: str,
    languages: list[str],
    activities: list[ProvenanceActivity] | None = None,
    evidence: list[EvidenceSpan] | None = None,
    coreference_links: list[CoreferenceLink] | None = None,
    conflicts: list[ConflictSet] | None = None,
    people: list[PersonMention] | None = None,
    relationships: list[RelationshipClaim] | None = None,
    events: list[FamilyEvent] | None = None,
    descriptions: list[PersonDescription] | None = None,
    stories: list[Story] | None = None,
    questions: list[UnresolvedQuestion] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        schema_version="extraction-v1",
        recording_id=recording_id,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        languages=languages,
        provenance_activities=activities or [],
        evidence_spans=evidence or [],
        coreference_links=coreference_links or [],
        conflict_sets=conflicts or [],
        people_mentions=people or [],
        relationship_claims=relationships or [],
        events=events or [],
        descriptions=descriptions or [],
        stories=stories or [],
        unresolved_questions=questions or [],
    )


def _semantic_code(object_type: str, message: str) -> ExtractionIssueCode:
    if object_type == "event" and "participant attribution" in message:
        return ExtractionIssueCode.EVENT_PARTICIPANT_ATTRIBUTION_UNSUPPORTED
    if object_type == "event" and any(
        token in message for token in ("unsupported description text", "unsupported title label")
    ):
        return ExtractionIssueCode.EVENT_STATEMENT_UNSUPPORTED
    if object_type == "description" and any(
        token in message
        for token in (
            "unsupported description text",
            "assigned to a person",
            "names a different person",
            "no evidence overlap",
            "unsupported perspective",
        )
    ):
        return ExtractionIssueCode.DESCRIPTION_ATTRIBUTION_UNSUPPORTED
    if object_type == "story" and any(
        token in message for token in ("unsupported summary text", "unsupported title label")
    ):
        return ExtractionIssueCode.STORY_STATEMENT_UNSUPPORTED
    if object_type == "relationship" and any(
        token in message
        for token in (
            "unsupported relationship endpoints",
            "contradicts deterministic",
            "deterministic kinship signal",
        )
    ):
        return ExtractionIssueCode.RELATIONSHIP_GROUNDING_REJECTED
    if any(
        token in message
        for token in ("unknown", "broken references", "references", "outside story evidence")
    ):
        return ExtractionIssueCode.OBJECT_REFERENCE_INVALID
    return ExtractionIssueCode.OBJECT_SEMANTIC_UNSUPPORTED


def _semantic_filter(
    *,
    items: list[ModelT],
    object_type: str,
    id_field: str,
    build_candidate: Callable[[ModelT], ExtractionResult],
    transcript: TranscriptEnvelope,
    cleaned: CleanerResult | None,
    issues: list[ExtractionIssue],
) -> list[ModelT]:
    accepted: list[ModelT] = []
    for item in items:
        object_id = str(getattr(item, id_field))
        try:
            validate_extraction_result(transcript, build_candidate(item), cleaned=cleaned)
        except ContractValidationError as exc:
            _issue(
                issues,
                object_type=object_type,
                object_id=object_id,
                stage=IssueStage.SEMANTIC,
                code=_semantic_code(object_type, str(exc)),
            )
            continue
        accepted.append(item)
    return accepted


def _evidence_recovery_issues(
    metrics: EvidenceOffsetRecoveryMetrics,
    issues: list[ExtractionIssue],
) -> None:
    code_by_reason = {
        "unknown_segment": ExtractionIssueCode.EVIDENCE_UNKNOWN_SEGMENT,
        "invalid_text": ExtractionIssueCode.EVIDENCE_EMPTY_TEXT,
        "wrong_source_layer": ExtractionIssueCode.EVIDENCE_WRONG_SOURCE_LAYER,
        "missing": ExtractionIssueCode.EVIDENCE_TEXT_NOT_IN_SOURCE,
        "ambiguous": ExtractionIssueCode.EVIDENCE_OFFSETS_AMBIGUOUS,
        "unrecoverable": ExtractionIssueCode.EVIDENCE_OFFSETS_UNRECOVERABLE,
    }
    for evidence_id, reason in metrics.quarantine_reasons:
        _issue(
            issues,
            object_type="evidence",
            object_id=evidence_id,
            stage=IssueStage.EVIDENCE_RECOVERY,
            code=code_by_reason.get(reason, ExtractionIssueCode.EVIDENCE_OFFSETS_UNRECOVERABLE),
        )


def process_extraction_candidate(
    *,
    raw: dict[str, Any],
    transcript: TranscriptEnvelope,
    speaker_id: str,
    speaker_name: str,
    cleaned: CleanerResult | None = None,
) -> ExtractionSanitizationOutcome:
    recovered_raw, recovery = recover_evidence_offsets(
        raw=raw,
        transcript=transcript,
        cleaned=cleaned,
    )
    issues: list[ExtractionIssue] = []
    _evidence_recovery_issues(recovery, issues)

    for key, expected in (
        ("recording_id", transcript.recording_id),
        ("speaker_id", speaker_id),
        ("speaker_name", speaker_name),
    ):
        if recovered_raw.get(key) != expected:
            _issue(
                issues,
                object_type="metadata",
                object_id=key,
                stage=IssueStage.SCHEMA,
                code=ExtractionIssueCode.AUTHORITATIVE_METADATA_USED,
                severity=IssueSeverity.WARNING,
                recoverable=True,
            )

    raw_languages = recovered_raw.get("languages", [])
    if isinstance(raw_languages, list) and all(isinstance(item, str) for item in raw_languages):
        languages = list(dict.fromkeys(raw_languages))
    else:
        languages = []
        _issue(
            issues,
            object_type="metadata",
            object_id="languages",
            stage=IssueStage.SCHEMA,
            code=ExtractionIssueCode.LANGUAGES_SCHEMA_INVALID,
        )

    activities = _parse_items(
        raw_items=_list_value(recovered_raw, "provenance_activities", issues),
        model_type=ProvenanceActivity,
        object_type="provenance_activity",
        id_field="activity_id",
        issues=issues,
    )
    evidence = _parse_items(
        raw_items=_list_value(recovered_raw, "evidence_spans", issues),
        model_type=EvidenceSpan,
        object_type="evidence",
        id_field="evidence_id",
        issues=issues,
        quarantined_ids=recovery.quarantined_evidence_ids,
    )
    coreference_links = _parse_items(
        raw_items=_list_value(recovered_raw, "coreference_links", issues),
        model_type=CoreferenceLink,
        object_type="coreference",
        id_field="coreference_id",
        issues=issues,
    )
    conflicts = _parse_items(
        raw_items=_list_value(recovered_raw, "conflict_sets", issues),
        model_type=ConflictSet,
        object_type="conflict",
        id_field="conflict_id",
        issues=issues,
    )
    people = _parse_items(
        raw_items=_list_value(recovered_raw, "people_mentions", issues),
        model_type=PersonMention,
        object_type="person",
        id_field="mention_id",
        issues=issues,
    )
    relationships = _parse_items(
        raw_items=_list_value(recovered_raw, "relationship_claims", issues),
        model_type=RelationshipClaim,
        object_type="relationship",
        id_field="relationship_id",
        issues=issues,
    )
    events = _parse_items(
        raw_items=_list_value(recovered_raw, "events", issues),
        model_type=FamilyEvent,
        object_type="event",
        id_field="event_id",
        issues=issues,
    )
    descriptions = _parse_items(
        raw_items=_list_value(recovered_raw, "descriptions", issues),
        model_type=PersonDescription,
        object_type="description",
        id_field="description_id",
        issues=issues,
    )
    stories = _parse_items(
        raw_items=_list_value(recovered_raw, "stories", issues),
        model_type=Story,
        object_type="story",
        id_field="story_id",
        issues=issues,
    )
    questions = _parse_items(
        raw_items=_list_value(recovered_raw, "unresolved_questions", issues),
        model_type=UnresolvedQuestion,
        object_type="question",
        id_field="question_id",
        issues=issues,
    )

    semantic_seed = _base_result(
        recording_id=transcript.recording_id,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        languages=languages,
        activities=activities,
        evidence=evidence,
        coreference_links=coreference_links,
        conflicts=conflicts,
        people=people,
        relationships=relationships,
        events=events,
        descriptions=descriptions,
        stories=stories,
        questions=questions,
    )
    semantic_seed, semantic_issues = harden_claim_semantics(
        semantic_seed,
        transcript,
        cleaned=cleaned,
    )
    issues.extend(semantic_issues)
    people = list(semantic_seed.people_mentions)
    relationships = list(semantic_seed.relationship_claims)
    events = list(semantic_seed.events)
    descriptions = list(semantic_seed.descriptions)
    stories = list(semantic_seed.stories)
    questions = list(semantic_seed.unresolved_questions)

    evidence_by_id = {item.evidence_id: item for item in evidence}
    sensitivity_rank = {
        StorySensitivity.NORMAL.value: 0,
        StorySensitivity.PERSONAL.value: 1,
        StorySensitivity.SENSITIVE.value: 2,
        StorySensitivity.HIGHLY_SENSITIVE.value: 3,
    }
    hardened_stories: list[Story] = []
    for story in stories:
        cited_text = " ".join(
            evidence_by_id[evidence_id].text
            for evidence_id in story.evidence_ids
            if evidence_id in evidence_by_id
        )
        inferred_level, reasons = sensitivity_level(cited_text)
        if sensitivity_rank[story.sensitivity.value] < sensitivity_rank[inferred_level]:
            _issue(
                issues,
                object_type="story",
                object_id=story.story_id,
                stage=IssueStage.PRIVACY,
                code=ExtractionIssueCode.STORY_SENSITIVITY_UPGRADED,
                severity=IssueSeverity.WARNING,
                recoverable=True,
            )
            story = story.model_copy(
                update={
                    "sensitivity": StorySensitivity(inferred_level),
                    "sensitivity_reasons": list(dict.fromkeys(reasons)),
                }
            )
        hardened_stories.append(story)
    stories = hardened_stories

    def build_result(
        *,
        selected_people: list[PersonMention] | None = None,
        selected_relationships: list[RelationshipClaim] | None = None,
        selected_events: list[FamilyEvent] | None = None,
        selected_descriptions: list[PersonDescription] | None = None,
        selected_stories: list[Story] | None = None,
        selected_questions: list[UnresolvedQuestion] | None = None,
    ) -> ExtractionResult:
        return _base_result(
            recording_id=transcript.recording_id,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            languages=languages,
            activities=activities,
            evidence=evidence,
            coreference_links=coreference_links,
            conflicts=conflicts,
            people=selected_people,
            relationships=selected_relationships,
            events=selected_events,
            descriptions=selected_descriptions,
            stories=selected_stories,
            questions=selected_questions,
        )

    valid_people = _semantic_filter(
        items=people,
        object_type="person",
        id_field="mention_id",
        build_candidate=lambda item: build_result(selected_people=[item]),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )

    preliminary = build_result(
        selected_people=valid_people,
        selected_relationships=relationships,
        selected_events=events,
        selected_descriptions=descriptions,
        selected_stories=stories,
        selected_questions=questions,
    )
    preliminary, evidence_closure_count = complete_relationship_evidence(preliminary, transcript)
    relationships = list(preliminary.relationship_claims)
    evidence = list(preliminary.evidence_spans)
    coreference_links = list(preliminary.coreference_links)

    valid_relationships = _semantic_filter(
        items=relationships,
        object_type="relationship",
        id_field="relationship_id",
        build_candidate=lambda item: build_result(
            selected_people=valid_people,
            selected_relationships=[item],
        ),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )
    valid_events = _semantic_filter(
        items=events,
        object_type="event",
        id_field="event_id",
        build_candidate=lambda item: build_result(
            selected_people=valid_people,
            selected_events=[item],
        ),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )
    valid_descriptions = _semantic_filter(
        items=descriptions,
        object_type="description",
        id_field="description_id",
        build_candidate=lambda item: build_result(
            selected_people=valid_people,
            selected_descriptions=[item],
        ),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )
    valid_stories = _semantic_filter(
        items=stories,
        object_type="story",
        id_field="story_id",
        build_candidate=lambda item: build_result(
            selected_people=valid_people,
            selected_events=valid_events,
            selected_stories=[item],
        ),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )
    valid_questions = _semantic_filter(
        items=questions,
        object_type="question",
        id_field="question_id",
        build_candidate=lambda item: build_result(
            selected_people=valid_people,
            selected_questions=[item],
        ),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )

    result = build_result(
        selected_people=valid_people,
        selected_relationships=valid_relationships,
        selected_events=valid_events,
        selected_descriptions=valid_descriptions,
        selected_stories=valid_stories,
        selected_questions=valid_questions,
    )
    result, claim_model_issues = materialize_extraction_contract_v2(
        result,
        transcript,
        cleaned=cleaned,
    )
    issues.extend(claim_model_issues)
    result, temporal_conflict_issues = add_temporal_conflicts(result)
    issues.extend(temporal_conflict_issues)

    def post_candidate(
        *,
        selected_relationships: list[RelationshipClaim] | None = None,
        selected_events: list[FamilyEvent] | None = None,
        selected_descriptions: list[PersonDescription] | None = None,
        selected_stories: list[Story] | None = None,
        selected_questions: list[UnresolvedQuestion] | None = None,
    ) -> ExtractionResult:
        # Semantic quarantine candidates must not contain unrelated invalid objects. Otherwise an
        # invalid later collection (for example a story with a missing event) can make an
        # independent valid event fail validation and collapse partial salvage.
        return result.model_copy(
            update={
                "schema_version": "extraction-v1",
                "conflict_sets": [],
                "relationship_claims": selected_relationships or [],
                "events": selected_events or [],
                "descriptions": selected_descriptions or [],
                "stories": selected_stories or [],
                "unresolved_questions": selected_questions or [],
            }
        )

    # Relationships were already semantically grounded before provenance materialization, and
    # materialization does not alter endpoints, roles, direction, or source segments. Revalidating
    # one relationship without its full open conflict set would incorrectly drop review candidates.
    post_relationships = list(result.relationship_claims)
    post_events = _semantic_filter(
        items=list(result.events),
        object_type="event",
        id_field="event_id",
        build_candidate=lambda item: post_candidate(selected_events=[item]),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )
    post_descriptions = _semantic_filter(
        items=list(result.descriptions),
        object_type="description",
        id_field="description_id",
        build_candidate=lambda item: post_candidate(selected_descriptions=[item]),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )
    post_stories = _semantic_filter(
        items=list(result.stories),
        object_type="story",
        id_field="story_id",
        build_candidate=lambda item: post_candidate(
            selected_events=[event for event in post_events if event.event_id in item.event_ids],
            selected_stories=[item],
        ),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )
    post_questions = _semantic_filter(
        items=list(result.unresolved_questions),
        object_type="question",
        id_field="question_id",
        build_candidate=lambda item: post_candidate(selected_questions=[item]),
        transcript=transcript,
        cleaned=cleaned,
        issues=issues,
    )
    result = result.model_copy(
        update={
            "relationship_claims": post_relationships,
            "events": post_events,
            "descriptions": post_descriptions,
            "stories": post_stories,
            "unresolved_questions": post_questions,
        }
    )
    result, conflict_issues = close_extraction_conflicts(result)
    issues.extend(conflict_issues)

    try:
        validate_extraction_result(transcript, result, cleaned=cleaned)
    except ContractValidationError:
        _issue(
            issues,
            object_type="extraction",
            object_id=None,
            stage=IssueStage.PROVENANCE,
            code=ExtractionIssueCode.FINAL_CONTRACT_INVALID,
            severity=IssueSeverity.FATAL,
        )
        raise

    serialized = [issue.to_dict() for issue in issues]
    return ExtractionSanitizationOutcome(
        recovered_raw=recovered_raw,
        result=result,
        issues=serialized,
        evidence_closure_count=evidence_closure_count,
        evidence_recovery=recovery,
    )


def sanitize_extraction_output(
    *,
    raw: dict[str, Any],
    transcript: TranscriptEnvelope,
    speaker_id: str,
    speaker_name: str,
    cleaned: CleanerResult | None = None,
) -> tuple[ExtractionResult, list[dict[str, Any]], int]:
    outcome = process_extraction_candidate(
        raw=raw,
        transcript=transcript,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        cleaned=cleaned,
    )
    return outcome.result, outcome.issues, outcome.evidence_closure_count
