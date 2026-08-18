from __future__ import annotations

import hashlib
from collections import Counter
from enum import StrEnum
from typing import Any

from pydantic import Field

from mura.domain.models import StrictModel


class IssueStage(StrEnum):
    SCHEMA = "schema"
    EVIDENCE_RECOVERY = "evidence_recovery"
    SEMANTIC = "semantic"
    PROVENANCE = "provenance"
    COREFERENCE = "coreference"
    PRIVACY = "privacy"
    REPAIR = "repair"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class ExtractionIssueCode(StrEnum):
    TOP_LEVEL_NOT_LIST = "top_level_not_list"
    OBJECT_SCHEMA_INVALID = "object_schema_invalid"
    DUPLICATE_OBJECT_ID = "duplicate_object_id"
    AUTHORITATIVE_METADATA_USED = "authoritative_metadata_used"
    LANGUAGES_SCHEMA_INVALID = "languages_schema_invalid"
    MODEL_PROVENANCE_REPLACED = "model_provenance_replaced"
    EVIDENCE_UNKNOWN_SEGMENT = "evidence_unknown_segment"
    EVIDENCE_EMPTY_TEXT = "evidence_empty_text"
    EVIDENCE_TEXT_NOT_IN_SOURCE = "evidence_text_not_in_source"
    EVIDENCE_WRONG_SOURCE_LAYER = "evidence_wrong_source_layer"
    EVIDENCE_OFFSETS_AMBIGUOUS = "evidence_offsets_ambiguous"
    EVIDENCE_OFFSETS_UNRECOVERABLE = "evidence_offsets_unrecoverable"
    EVIDENCE_UNKNOWN_MENTION = "evidence_unknown_mention"
    EVIDENCE_DERIVATION_UNKNOWN = "evidence_derivation_unknown"
    EVIDENCE_DERIVATION_CYCLE = "evidence_derivation_cycle"
    OBJECT_UNKNOWN_EVIDENCE = "object_unknown_evidence"
    OBJECT_EVIDENCE_OUT_OF_SCOPE = "object_evidence_out_of_scope"
    OBJECT_MISSING_EVIDENCE = "object_missing_evidence"
    OBJECT_REFERENCE_INVALID = "object_reference_invalid"
    OBJECT_SEMANTIC_UNSUPPORTED = "object_semantic_unsupported"
    PERSON_ALIAS_UNSUPPORTED = "person_alias_unsupported"
    PERSON_CATEGORY_DOWNGRADED = "person_category_downgraded"
    PERSON_RELATION_REMOVED = "person_relation_removed"
    RELATIONSHIP_GROUNDING_REJECTED = "relationship_grounding_rejected"
    COREFERENCE_REFERENCE_INVALID = "coreference_reference_invalid"
    COREFERENCE_ANAPHOR_UNSUPPORTED = "coreference_anaphor_unsupported"
    CONFLICT_REFERENCE_INVALID = "conflict_reference_invalid"
    VERIFICATION_STATUS_DOWNGRADED = "verification_status_downgraded"
    STORY_PRIVACY_FORCED_PRIVATE = "story_privacy_forced_private"
    UNCERTAINTY_SCOPE_AMBIGUOUS = "uncertainty_scope_ambiguous"
    UNCERTAINTY_MARKER_UNSUPPORTED = "uncertainty_marker_unsupported"
    REPORTED_SPEECH_REQUIRES_REVIEW = "reported_speech_requires_review"
    TEMPORAL_VALUE_INVALID = "temporal_value_invalid"
    TEMPORAL_PRECISION_OVERSTATED = "temporal_precision_overstated"
    TEMPORAL_RANGE_INVALID = "temporal_range_invalid"
    TEMPORAL_ANCHOR_MISSING = "temporal_anchor_missing"
    TEMPORAL_CONFLICT_DETECTED = "temporal_conflict_detected"
    TEMPORAL_FORMAT_AMBIGUOUS = "temporal_format_ambiguous"
    TEMPORAL_EXPRESSION_UNRESOLVED = "temporal_expression_unresolved"
    TEMPORAL_EVIDENCE_UNSUPPORTED = "temporal_evidence_unsupported"
    RELATIONSHIP_FORMER_NOT_ACTIVE = "relationship_former_not_active"
    RELATIONSHIP_ENDED_NOT_ACTIVE = "relationship_ended_not_active"
    RELATIONSHIP_NEGATED = "relationship_negated"
    RELATIONSHIP_FIGURATIVE = "relationship_figurative"
    RELATIONSHIP_STATE_CONFLICT = "relationship_state_conflict"
    SELF_CORRECTION_APPLIED = "self_correction_applied"
    SELF_CORRECTION_AMBIGUOUS = "self_correction_ambiguous"
    DERIVED_CLAIM_SELF_REFERENCE = "derived_claim_self_reference"
    DERIVED_CLAIM_DUPLICATE = "derived_claim_duplicate"
    FINAL_CONTRACT_INVALID = "final_contract_invalid"
    REPAIR_REQUIRED = "repair_required"
    REPAIR_FAILED = "repair_failed"
    FOCUSED_PASS_CONTRACT_INVALID = "focused_pass_contract_invalid"
    FOCUSED_PASS_FAILED = "focused_pass_failed"
    DUPLICATE_SEMANTIC_OBJECT = "duplicate_semantic_object"
    EVENT_STATEMENT_UNSUPPORTED = "event_statement_unsupported"
    EVENT_PARTICIPANT_ATTRIBUTION_UNSUPPORTED = "event_participant_attribution_unsupported"
    DESCRIPTION_ATTRIBUTION_UNSUPPORTED = "description_attribution_unsupported"
    STORY_STATEMENT_UNSUPPORTED = "story_statement_unsupported"
    STORY_SENSITIVITY_UPGRADED = "story_sensitivity_upgraded"
    LONG_FORM_WINDOW_FAILED = "long_form_window_failed"
    LONG_FORM_WINDOW_BUDGET_EXHAUSTED = "long_form_window_budget_exhausted"
    LONG_FORM_WINDOW_TIMEOUT = "long_form_window_timeout"
    LONG_FORM_PARTIAL_COMPLETION = "long_form_partial_completion"
    LONG_FORM_MERGE_COLLISION = "long_form_merge_collision"
    LONG_FORM_CROSS_WINDOW_REFERENCE_INVALID = "long_form_cross_window_reference_invalid"


_DETAIL_BY_CODE: dict[ExtractionIssueCode, str] = {
    ExtractionIssueCode.TOP_LEVEL_NOT_LIST: "A top-level extraction collection had the wrong type.",
    ExtractionIssueCode.OBJECT_SCHEMA_INVALID: "An extraction object failed schema validation.",
    ExtractionIssueCode.DUPLICATE_OBJECT_ID: (
        "A duplicate extraction object identifier was quarantined."
    ),
    ExtractionIssueCode.AUTHORITATIVE_METADATA_USED: (
        "Authoritative request metadata replaced model-provided metadata."
    ),
    ExtractionIssueCode.LANGUAGES_SCHEMA_INVALID: "The languages field failed schema validation.",
    ExtractionIssueCode.MODEL_PROVENANCE_REPLACED: (
        "Model-provided provenance activity data was replaced."
    ),
    ExtractionIssueCode.EVIDENCE_UNKNOWN_SEGMENT: (
        "Evidence referenced a segment outside the current transcript."
    ),
    ExtractionIssueCode.EVIDENCE_EMPTY_TEXT: "Evidence text was empty or invalid.",
    ExtractionIssueCode.EVIDENCE_TEXT_NOT_IN_SOURCE: (
        "Evidence text was not an exact substring of its declared source layer."
    ),
    ExtractionIssueCode.EVIDENCE_WRONG_SOURCE_LAYER: (
        "Evidence text existed only in a different transcript source layer."
    ),
    ExtractionIssueCode.EVIDENCE_OFFSETS_AMBIGUOUS: (
        "Evidence offsets could not be recovered because the exact text was ambiguous."
    ),
    ExtractionIssueCode.EVIDENCE_OFFSETS_UNRECOVERABLE: (
        "Evidence offsets could not be deterministically recovered."
    ),
    ExtractionIssueCode.EVIDENCE_UNKNOWN_MENTION: "Evidence referenced an unknown person mention.",
    ExtractionIssueCode.EVIDENCE_DERIVATION_UNKNOWN: (
        "Derived evidence referenced an unknown evidence span."
    ),
    ExtractionIssueCode.EVIDENCE_DERIVATION_CYCLE: "The derived evidence graph contained a cycle.",
    ExtractionIssueCode.OBJECT_UNKNOWN_EVIDENCE: "The object referenced unknown evidence.",
    ExtractionIssueCode.OBJECT_EVIDENCE_OUT_OF_SCOPE: (
        "The object cited evidence outside its source segments."
    ),
    ExtractionIssueCode.OBJECT_MISSING_EVIDENCE: (
        "The object had no sufficient source-linked evidence."
    ),
    ExtractionIssueCode.OBJECT_REFERENCE_INVALID: (
        "The object contained an invalid cross-object reference."
    ),
    ExtractionIssueCode.OBJECT_SEMANTIC_UNSUPPORTED: (
        "The object was not supported by its cited source evidence."
    ),
    ExtractionIssueCode.PERSON_ALIAS_UNSUPPORTED: (
        "A person alias lacked an explicit source-linked alias cue and was removed."
    ),
    ExtractionIssueCode.PERSON_CATEGORY_DOWNGRADED: (
        "A person category lacked sufficient source support and was downgraded."
    ),
    ExtractionIssueCode.PERSON_RELATION_REMOVED: (
        "A relation-to-speaker label lacked sufficient source support and was removed."
    ),
    ExtractionIssueCode.RELATIONSHIP_GROUNDING_REJECTED: (
        "The relationship lacked deterministic endpoint-specific grounding."
    ),
    ExtractionIssueCode.COREFERENCE_REFERENCE_INVALID: (
        "The coreference link contained an invalid reference."
    ),
    ExtractionIssueCode.COREFERENCE_ANAPHOR_UNSUPPORTED: (
        "The coreference anaphor was not present in cited evidence."
    ),
    ExtractionIssueCode.CONFLICT_REFERENCE_INVALID: (
        "The conflict set contained an invalid claim or evidence reference."
    ),
    ExtractionIssueCode.VERIFICATION_STATUS_DOWNGRADED: (
        "A model-provided verification status was forced to unreviewed."
    ),
    ExtractionIssueCode.STORY_PRIVACY_FORCED_PRIVATE: (
        "A model-provided story privacy value was forced to private."
    ),
    ExtractionIssueCode.UNCERTAINTY_SCOPE_AMBIGUOUS: (
        "An uncertainty marker could not be assigned to exactly one local claim scope."
    ),
    ExtractionIssueCode.UNCERTAINTY_MARKER_UNSUPPORTED: (
        "An uncertain assertion lacked a supported local linguistic marker."
    ),
    ExtractionIssueCode.REPORTED_SPEECH_REQUIRES_REVIEW: (
        "A quoted assertion was retained as reported speech and requires review."
    ),
    ExtractionIssueCode.TEMPORAL_VALUE_INVALID: "A temporal value was not a valid calendar value.",
    ExtractionIssueCode.TEMPORAL_PRECISION_OVERSTATED: (
        "A model-proposed temporal value claimed more precision than the source expression."
    ),
    ExtractionIssueCode.TEMPORAL_RANGE_INVALID: "A temporal range had invalid or reversed bounds.",
    ExtractionIssueCode.TEMPORAL_ANCHOR_MISSING: (
        "A relative temporal expression lacked a deterministic source-linked anchor."
    ),
    ExtractionIssueCode.TEMPORAL_CONFLICT_DETECTED: (
        "Supported temporal claims disagreed and were retained for review."
    ),
    ExtractionIssueCode.TEMPORAL_FORMAT_AMBIGUOUS: (
        "A numeric temporal format was locale-ambiguous and was not exactified."
    ),
    ExtractionIssueCode.TEMPORAL_EXPRESSION_UNRESOLVED: (
        "A temporal expression was preserved without unsupported normalization."
    ),
    ExtractionIssueCode.TEMPORAL_EVIDENCE_UNSUPPORTED: (
        "A temporal expression was absent from the object's source evidence."
    ),
    ExtractionIssueCode.RELATIONSHIP_FORMER_NOT_ACTIVE: (
        "A former relationship was retained as history and excluded from the active graph."
    ),
    ExtractionIssueCode.RELATIONSHIP_ENDED_NOT_ACTIVE: (
        "An ended relationship was retained as history and excluded from the active graph."
    ),
    ExtractionIssueCode.RELATIONSHIP_NEGATED: (
        "A negated relationship was excluded from positive family memory."
    ),
    ExtractionIssueCode.RELATIONSHIP_FIGURATIVE: (
        "A figurative or social comparison was excluded from biological/legal kinship."
    ),
    ExtractionIssueCode.RELATIONSHIP_STATE_CONFLICT: (
        "Relationship-state evidence conflicted and requires review."
    ),
    ExtractionIssueCode.SELF_CORRECTION_APPLIED: (
        "An explicit speaker self-correction prevented the superseded claim from becoming active."
    ),
    ExtractionIssueCode.SELF_CORRECTION_AMBIGUOUS: (
        "A possible self-correction could not be assigned safely and requires review."
    ),
    ExtractionIssueCode.DERIVED_CLAIM_SELF_REFERENCE: (
        "A claim self-reference was removed from derived provenance."
    ),
    ExtractionIssueCode.DERIVED_CLAIM_DUPLICATE: "Duplicate derived claim references were removed.",
    ExtractionIssueCode.FINAL_CONTRACT_INVALID: "The final extraction contract failed validation.",
    ExtractionIssueCode.REPAIR_REQUIRED: (
        "A fatal top-level extraction contract error required one repair attempt."
    ),
    ExtractionIssueCode.REPAIR_FAILED: "The extraction repair response remained unusable.",
    ExtractionIssueCode.FOCUSED_PASS_CONTRACT_INVALID: (
        "A focused extraction pass returned a payload outside its bounded contract."
    ),
    ExtractionIssueCode.FOCUSED_PASS_FAILED: (
        "A focused extraction pass failed safely without removing earlier accepted objects."
    ),
    ExtractionIssueCode.DUPLICATE_SEMANTIC_OBJECT: (
        "A semantically duplicate focused-pass object was removed deterministically."
    ),
    ExtractionIssueCode.EVENT_STATEMENT_UNSUPPORTED: (
        "An event statement changed source order, polarity, causality, or factual content."
    ),
    ExtractionIssueCode.EVENT_PARTICIPANT_ATTRIBUTION_UNSUPPORTED: (
        "An event participant was not supported by the event statement."
    ),
    ExtractionIssueCode.DESCRIPTION_ATTRIBUTION_UNSUPPORTED: (
        "A person description was not safely attributable to its target."
    ),
    ExtractionIssueCode.STORY_STATEMENT_UNSUPPORTED: (
        "A story summary statement was not supported by episode evidence."
    ),
    ExtractionIssueCode.STORY_SENSITIVITY_UPGRADED: (
        "Story sensitivity was conservatively upgraded from source evidence."
    ),
    ExtractionIssueCode.LONG_FORM_WINDOW_FAILED: (
        "A bounded long-form window failed without discarding other accepted windows."
    ),
    ExtractionIssueCode.LONG_FORM_WINDOW_BUDGET_EXHAUSTED: (
        "A bounded long-form window was skipped because the typed model budget was exhausted."
    ),
    ExtractionIssueCode.LONG_FORM_WINDOW_TIMEOUT: (
        "A bounded long-form window exceeded the provider processing deadline."
    ),
    ExtractionIssueCode.LONG_FORM_PARTIAL_COMPLETION: (
        "The recording completed with at least one failed or skipped bounded window."
    ),
    ExtractionIssueCode.LONG_FORM_MERGE_COLLISION: (
        "A cross-window identifier collision was retained for deterministic review."
    ),
    ExtractionIssueCode.LONG_FORM_CROSS_WINDOW_REFERENCE_INVALID: (
        "A cross-window reference could not be remapped to a recording-global object."
    ),
}


def opaque_issue_id(value: str | None) -> str | None:
    """Return a stable non-reversible identifier safe for processing metadata."""

    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"object_{digest}"


class ExtractionIssue(StrictModel):
    stage: IssueStage
    object_type: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    object_id: str | None = None
    code: ExtractionIssueCode
    severity: IssueSeverity = IssueSeverity.ERROR
    recoverable: bool = False
    detail_safe: str = Field(min_length=1)
    related_ids: list[str] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        stage: IssueStage | str,
        object_type: str,
        object_id: str | None,
        code: ExtractionIssueCode,
        severity: IssueSeverity = IssueSeverity.ERROR,
        recoverable: bool = False,
        related_ids: list[str] | None = None,
    ) -> ExtractionIssue:
        return cls(
            stage=IssueStage(stage),
            object_type=object_type,
            object_id=object_id,
            code=code,
            severity=severity,
            recoverable=recoverable,
            detail_safe=_DETAIL_BY_CODE[code],
            related_ids=list(dict.fromkeys(related_ids or [])),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        # Compatibility for downstream consumers that still display `detail`.
        payload["detail"] = self.detail_safe
        return payload


def privacy_safe_issue_payload(issue: dict[str, Any]) -> dict[str, Any]:
    """Remove user-controlled identifiers before an issue enters telemetry/traces."""

    payload = dict(issue)
    object_id = payload.get("object_id")
    payload["object_id"] = opaque_issue_id(object_id) if isinstance(object_id, str) else None
    related = payload.get("related_ids", [])
    payload["related_ids"] = [
        safe_id
        for value in related
        if isinstance(value, str) and (safe_id := opaque_issue_id(value)) is not None
    ]
    payload.pop("detail", None)
    return payload


def privacy_safe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [privacy_safe_issue_payload(issue) for issue in issues]


def safe_issue_counts(issues: list[dict[str, Any]] | list[ExtractionIssue]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for issue in issues:
        if isinstance(issue, ExtractionIssue):
            counts[issue.code.value] += 1
            continue
        code = issue.get("code")
        if isinstance(code, str):
            counts[code] += 1
    return dict(sorted(counts.items()))
