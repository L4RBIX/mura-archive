from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import Field

from mura.domain.models import (
    CoreferenceLink,
    EvidenceSpan,
    FamilyEvent,
    PersonDescription,
    PersonMention,
    RelationshipClaim,
    Story,
    StrictModel,
    UnresolvedQuestion,
)
from mura.relationship_evidence import normalize_evidence


class FocusedExtractionPass(StrEnum):
    CORE = "core"
    EVENTS = "events"
    STORIES = "stories"


class _PassIdentity(StrictModel):
    recording_id: str
    speaker_id: str
    speaker_name: str
    languages: list[str] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)


class CorePassOutput(_PassIdentity):
    people_mentions: list[PersonMention] = Field(default_factory=list)
    relationship_claims: list[RelationshipClaim] = Field(default_factory=list)
    coreference_links: list[CoreferenceLink] = Field(default_factory=list)


class EventPassOutput(_PassIdentity):
    events: list[FamilyEvent] = Field(default_factory=list)
    descriptions: list[PersonDescription] = Field(default_factory=list)


class StoryPassOutput(_PassIdentity):
    stories: list[Story] = Field(default_factory=list)
    unresolved_questions: list[UnresolvedQuestion] = Field(default_factory=list)


PASS_MODEL: dict[FocusedExtractionPass, type[_PassIdentity]] = {
    FocusedExtractionPass.CORE: CorePassOutput,
    FocusedExtractionPass.EVENTS: EventPassOutput,
    FocusedExtractionPass.STORIES: StoryPassOutput,
}


@dataclass(frozen=True)
class PassMergeMetrics:
    deduplicated_events: int = 0
    deduplicated_descriptions: int = 0
    deduplicated_stories: int = 0
    deduplicated_questions: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "deduplicated_events": self.deduplicated_events,
            "deduplicated_descriptions": self.deduplicated_descriptions,
            "deduplicated_stories": self.deduplicated_stories,
            "deduplicated_questions": self.deduplicated_questions,
        }


def pass_output_schema(pass_name: FocusedExtractionPass) -> dict[str, Any]:
    return PASS_MODEL[pass_name].model_json_schema()


_COMMON_PASS_FIELDS = {
    "recording_id",
    "speaker_id",
    "speaker_name",
    "languages",
    "evidence_spans",
}
_PASS_FIELDS = {
    FocusedExtractionPass.CORE: {"people_mentions", "relationship_claims", "coreference_links"},
    FocusedExtractionPass.EVENTS: {"events", "descriptions"},
    FocusedExtractionPass.STORIES: {"stories", "unresolved_questions"},
}


def validate_pass_identity(
    pass_name: FocusedExtractionPass,
    raw: dict[str, Any],
    *,
    recording_id: str,
    speaker_id: str,
    speaker_name: str,
) -> None:
    if not isinstance(raw, dict):
        raise ValueError("focused pass output must be an object")
    allowed = _COMMON_PASS_FIELDS.union(_PASS_FIELDS[pass_name])
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError("focused pass returned disallowed top-level fields")
    if raw.get("recording_id") != recording_id:
        raise ValueError("focused pass recording_id mismatch")
    if raw.get("speaker_id") != speaker_id or raw.get("speaker_name") != speaker_name:
        raise ValueError("focused pass speaker identity mismatch")
    for field in {"languages", "evidence_spans", *_PASS_FIELDS[pass_name]}:
        if not isinstance(raw.get(field, []), list):
            raise ValueError(f"focused pass field {field} must be a list")


def _namespace_id(prefix: str, value: str) -> str:
    if value.startswith(f"{prefix}__"):
        return value
    return f"{prefix}__{value}"


def _rewrite_evidence_references(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_rewrite_evidence_references(item, mapping) for item in value]
    if not isinstance(value, dict):
        return value
    rewritten: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"evidence_ids", "state_evidence_ids", "source_evidence_ids"} and isinstance(
            item, list
        ):
            rewritten[key] = [mapping.get(str(item_id), str(item_id)) for item_id in item]
        elif key == "evidence_id" and isinstance(item, str):
            rewritten[key] = mapping.get(item, item)
        elif key == "derived_from_evidence_ids" and isinstance(item, list):
            rewritten[key] = [mapping.get(str(item_id), str(item_id)) for item_id in item]
        else:
            rewritten[key] = _rewrite_evidence_references(item, mapping)
    return rewritten


def namespace_pass_output(
    pass_name: FocusedExtractionPass,
    raw: dict[str, Any],
) -> dict[str, Any]:
    candidate = deepcopy(raw)
    evidence_items = candidate.get("evidence_spans", [])
    mapping: dict[str, str] = {}
    if isinstance(evidence_items, list):
        for item in evidence_items:
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str):
                old_id = item["evidence_id"]
                mapping[old_id] = _namespace_id(pass_name.value, old_id)
    return _rewrite_evidence_references(candidate, mapping)


def empty_extraction_raw(
    *,
    recording_id: str,
    speaker_id: str,
    speaker_name: str,
) -> dict[str, Any]:
    return {
        "schema_version": "extraction-v2",
        "recording_id": recording_id,
        "speaker_id": speaker_id,
        "speaker_name": speaker_name,
        "languages": [],
        "provenance_activities": [],
        "evidence_spans": [],
        "coreference_links": [],
        "conflict_sets": [],
        "people_mentions": [],
        "relationship_claims": [],
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }


def _deduplicate(
    items: list[dict[str, Any]],
    *,
    key_fn: Any,
) -> tuple[list[dict[str, Any]], int]:
    accepted: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    dropped = 0
    for item in items:
        key = key_fn(item)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        accepted.append(item)
    return accepted, dropped


def _event_key(item: dict[str, Any]) -> tuple[Any, ...]:
    raw_date = item.get("date")
    date: dict[str, Any] = raw_date if isinstance(raw_date, dict) else {}
    return (
        normalize_evidence(str(item.get("event_type", ""))),
        tuple(sorted(str(value) for value in item.get("participant_mention_ids", []))),
        normalize_evidence(str(date.get("original_expression", ""))),
        normalize_evidence(str(item.get("location", ""))),
        tuple(sorted(str(value) for value in item.get("source_segment_ids", []))),
    )


def _description_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(item.get("person_mention_id", "")),
        normalize_evidence(str(item.get("description", ""))),
        normalize_evidence(str(item.get("perspective", ""))),
        tuple(sorted(str(value) for value in item.get("source_segment_ids", []))),
    )


def _story_key(item: dict[str, Any]) -> tuple[Any, ...]:
    # Segment scope is part of the key so two episodes with the same people are not collapsed.
    return (
        tuple(sorted(str(value) for value in item.get("source_segment_ids", []))),
        normalize_evidence(str(item.get("summary", ""))),
    )


def _question_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        normalize_evidence(str(item.get("question", ""))),
        tuple(sorted(str(value) for value in item.get("source_segment_ids", []))),
    )


def merge_focused_pass(
    base_raw: dict[str, Any],
    pass_name: FocusedExtractionPass,
    pass_raw: dict[str, Any],
) -> tuple[dict[str, Any], PassMergeMetrics]:
    merged = deepcopy(base_raw)
    candidate = namespace_pass_output(pass_name, pass_raw)
    merged["languages"] = list(
        dict.fromkeys([*merged.get("languages", []), *candidate.get("languages", [])])
    )
    merged["evidence_spans"] = [
        *merged.get("evidence_spans", []),
        *candidate.get("evidence_spans", []),
    ]

    if pass_name is FocusedExtractionPass.CORE:
        merged["people_mentions"] = candidate.get("people_mentions", [])
        merged["relationship_claims"] = candidate.get("relationship_claims", [])
        merged["coreference_links"] = candidate.get("coreference_links", [])
        return merged, PassMergeMetrics()

    if pass_name is FocusedExtractionPass.EVENTS:
        events, event_duplicates = _deduplicate(candidate.get("events", []), key_fn=_event_key)
        descriptions, description_duplicates = _deduplicate(
            candidate.get("descriptions", []), key_fn=_description_key
        )
        merged["events"] = events
        merged["descriptions"] = descriptions
        return merged, PassMergeMetrics(
            deduplicated_events=event_duplicates,
            deduplicated_descriptions=description_duplicates,
        )

    stories, story_duplicates = _deduplicate(candidate.get("stories", []), key_fn=_story_key)
    questions, question_duplicates = _deduplicate(
        candidate.get("unresolved_questions", []), key_fn=_question_key
    )
    merged["stories"] = stories
    merged["unresolved_questions"] = questions
    return merged, PassMergeMetrics(
        deduplicated_stories=story_duplicates,
        deduplicated_questions=question_duplicates,
    )


def accepted_context(result: Any, pass_name: FocusedExtractionPass) -> dict[str, Any]:
    people = [
        {
            "mention_id": item.mention_id,
            "name": item.name,
            "aliases": item.aliases,
            "category": item.category.value,
            "source_segment_ids": item.source_segment_ids,
            "evidence_ids": item.evidence_ids,
        }
        for item in result.people_mentions
    ]
    if pass_name is FocusedExtractionPass.EVENTS:
        return {
            "accepted_people": people,
            "allowed_person_mention_ids": [person["mention_id"] for person in people],
        }
    events = [
        {
            "event_id": item.event_id,
            "event_type": item.event_type,
            "title": item.title,
            "participant_mention_ids": item.participant_mention_ids,
            "date": item.date.model_dump(mode="json") if item.date is not None else None,
            "location": item.location,
            "source_segment_ids": item.source_segment_ids,
            "evidence_ids": item.evidence_ids,
        }
        for item in result.events
    ]
    return {
        "accepted_people": people,
        "accepted_events": events,
        "allowed_person_mention_ids": [p["mention_id"] for p in people],
        "allowed_event_ids": [e["event_id"] for e in events],
    }
