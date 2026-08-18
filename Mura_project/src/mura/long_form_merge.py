from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from pydantic import Field

from mura.domain.models import ExtractionResult, StrictModel
from mura.long_form import TranscriptWindow

MERGE_VERSION = "long-form-merge-v1"
REGISTRY_VERSION = "recording-mention-registry-v1-conservative"

_ID_FIELDS = (
    "activity_id",
    "evidence_id",
    "coreference_id",
    "conflict_id",
    "mention_id",
    "relationship_id",
    "event_id",
    "description_id",
    "story_id",
    "question_id",
    "variant_id",
)


class WindowExtraction(StrictModel):
    window: TranscriptWindow
    extraction: ExtractionResult


class MergeReport(StrictModel):
    merge_version: str = MERGE_VERSION
    registry_version: str = REGISTRY_VERSION
    accepted: int = Field(ge=0)
    deduplicated: int = Field(ge=0)
    conflicted: int = Field(ge=0)
    quarantined: int = Field(ge=0)
    remapped: int = Field(ge=0)
    review_required: int = Field(ge=0)
    duplicate_people: int = Field(ge=0)
    duplicate_relationships: int = Field(ge=0)
    duplicate_events: int = Field(ge=0)
    duplicate_stories: int = Field(ge=0)


def _stable_id(prefix: str, *parts: str) -> str:
    material = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(material).hexdigest()[:32]}"


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.replace("_", " ").split())


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _walk(value: object) -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _ID_FIELDS and isinstance(item, str) and item:
                yield key, item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _replace_ids(value: object, mapping: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {key: _replace_ids(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_ids(item, mapping) for item in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def _id_prefix(field_name: str) -> str:
    return {
        "activity_id": "activity",
        "evidence_id": "evidence",
        "coreference_id": "coreference",
        "conflict_id": "conflict",
        "mention_id": "mention",
        "relationship_id": "relationship",
        "event_id": "event",
        "description_id": "description",
        "story_id": "story",
        "question_id": "question",
        "variant_id": "variant",
    }[field_name]


def _remap_window(item: WindowExtraction) -> tuple[dict[str, Any], int]:
    raw = item.extraction.model_dump(mode="json")
    mapping: dict[str, str] = {}
    for field_name, local_id in _walk(raw):
        mapping.setdefault(
            local_id,
            _stable_id(
                _id_prefix(field_name),
                item.extraction.recording_id,
                item.window.window_id,
                field_name,
                local_id,
            ),
        )
    remapped = _replace_ids(raw, mapping)
    assert isinstance(remapped, dict)
    return remapped, len(mapping)


def _source_ids(item: dict[str, Any]) -> set[str]:
    values = item.get("source_segment_ids", [])
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str)}


def _merge_references(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key in (
        "source_segment_ids",
        "evidence_ids",
        "coreference_link_ids",
        "conflict_ids",
        "state_evidence_ids",
        "participant_mention_ids",
        "person_mention_ids",
        "event_ids",
        "related_mention_ids",
    ):
        left = target.get(key)
        right = incoming.get(key)
        if isinstance(left, list) and isinstance(right, list):
            target[key] = list(dict.fromkeys([*left, *right]))


def _deduplicate_people(raws: list[dict[str, Any]]) -> tuple[dict[str, str], int, int]:
    people: list[dict[str, Any]] = []
    for raw in raws:
        people.extend(raw.get("people_mentions", []))
    mapping: dict[str, str] = {}
    duplicates = 0
    review_required = 0
    accepted: list[dict[str, Any]] = []
    by_name: dict[str, list[dict[str, Any]]] = {}
    for person in people:
        name = _normalize(str(person.get("name", "")))
        candidates = by_name.get(name, [])
        duplicate = next(
            (
                candidate
                for candidate in candidates
                if _source_ids(candidate).intersection(_source_ids(person))
            ),
            None,
        )
        if duplicate is None:
            if candidates:
                review_required += 1
            accepted.append(person)
            by_name.setdefault(name, []).append(person)
            continue
        old_id = person.get("mention_id")
        canonical_id = duplicate.get("mention_id")
        if isinstance(old_id, str) and isinstance(canonical_id, str):
            mapping[old_id] = canonical_id
        _merge_references(duplicate, person)
        duplicate["aliases"] = list(
            dict.fromkeys([*duplicate.get("aliases", []), *person.get("aliases", [])])
        )
        duplicates += 1
    for raw in raws:
        raw["people_mentions"] = [
            item for item in accepted if item in raw.get("people_mentions", [])
        ]
    return mapping, duplicates, review_required


def _replace_all(raws: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    if not mapping:
        return raws
    updated = _replace_ids(raws, mapping)
    assert isinstance(updated, list)
    return updated


def _object_signature(collection: str, item: dict[str, Any]) -> tuple[object, ...]:
    if collection == "relationship_claims":
        endpoints = (
            item.get("subject_mention_id"),
            item.get("subject_role"),
            item.get("object_mention_id"),
            item.get("object_role"),
        )
        if item.get("relationship_type") in {"spouse", "sibling"}:
            endpoint_pairs = sorted(
                (
                    (str(endpoints[0]), str(endpoints[1])),
                    (str(endpoints[2]), str(endpoints[3])),
                )
            )
            endpoints = (*endpoint_pairs[0], *endpoint_pairs[1])
        return (
            item.get("relationship_type"),
            item.get("relationship_state"),
            *endpoints,
            item.get("assertion_mode"),
        )
    if collection == "events":
        date = item.get("date")
        return (
            _normalize(str(item.get("event_type", ""))),
            _normalize(str(item.get("title", ""))),
            tuple(sorted(item.get("participant_mention_ids", []))),
            _canonical(date),
            _normalize(str(item.get("location", ""))),
        )
    if collection == "descriptions":
        return (
            item.get("person_mention_id"),
            _normalize(str(item.get("description", ""))),
            _normalize(str(item.get("perspective", ""))),
        )
    if collection == "stories":
        return (
            _normalize(str(item.get("title", ""))),
            _normalize(str(item.get("summary", ""))),
            tuple(sorted(item.get("person_mention_ids", []))),
            tuple(sorted(item.get("event_ids", []))),
        )
    if collection == "unresolved_questions":
        return (
            _normalize(str(item.get("question", ""))),
            tuple(sorted(item.get("related_mention_ids", []))),
        )
    raise ValueError(f"unsupported merge collection {collection}")


def _deduplicate_collection(
    items: list[dict[str, Any]],
    collection: str,
) -> tuple[list[dict[str, Any]], dict[str, str], int]:
    accepted: list[dict[str, Any]] = []
    by_signature: dict[tuple[object, ...], list[dict[str, Any]]] = {}
    mapping: dict[str, str] = {}
    duplicates = 0
    id_field = {
        "relationship_claims": "relationship_id",
        "events": "event_id",
        "descriptions": "description_id",
        "stories": "story_id",
        "unresolved_questions": "question_id",
    }[collection]
    for item in items:
        signature = _object_signature(collection, item)
        candidates = by_signature.get(signature, [])
        duplicate = next(
            (
                candidate
                for candidate in candidates
                if not _source_ids(candidate)
                or not _source_ids(item)
                or _source_ids(candidate).intersection(_source_ids(item))
                or collection in {"relationship_claims", "descriptions", "unresolved_questions"}
            ),
            None,
        )
        if duplicate is None:
            accepted.append(item)
            by_signature.setdefault(signature, []).append(item)
            continue
        old_id = item.get(id_field)
        canonical_id = duplicate.get(id_field)
        if isinstance(old_id, str) and isinstance(canonical_id, str):
            mapping[old_id] = canonical_id
        _merge_references(duplicate, item)
        duplicates += 1
    return accepted, mapping, duplicates


def _deduplicate_evidence(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], int]:
    accepted: list[dict[str, Any]] = []
    by_signature: dict[tuple[object, ...], dict[str, Any]] = {}
    mapping: dict[str, str] = {}
    duplicates = 0
    for item in items:
        signature = (
            item.get("segment_id"),
            item.get("text"),
            item.get("source_layer"),
            item.get("start_char"),
            item.get("end_char"),
            item.get("evidence_class"),
        )
        duplicate = by_signature.get(signature)
        if duplicate is None:
            accepted.append(item)
            by_signature[signature] = item
            continue
        old_id = item.get("evidence_id")
        canonical_id = duplicate.get("evidence_id")
        if isinstance(old_id, str) and isinstance(canonical_id, str):
            mapping[old_id] = canonical_id
        for key in (
            "purposes",
            "mention_ids",
            "coreference_link_ids",
            "derived_from_evidence_ids",
        ):
            duplicate[key] = list(dict.fromkeys([*duplicate.get(key, []), *item.get(key, [])]))
        duplicates += 1
    return accepted, mapping, duplicates


def merge_window_extractions(
    *,
    recording_id: str,
    speaker_id: str,
    speaker_name: str,
    windows: list[WindowExtraction],
) -> tuple[ExtractionResult, MergeReport]:
    if not windows:
        raise ValueError("at least one successful window is required")
    remapped_count = 0
    raws: list[dict[str, Any]] = []
    for window in sorted(windows, key=lambda item: item.window.ordinal):
        remapped, count = _remap_window(window)
        raws.append(remapped)
        remapped_count += count

    mention_mapping, duplicate_people, review_required = _deduplicate_people(raws)
    raws = _replace_all(raws, mention_mapping)

    combined: dict[str, Any] = {
        "schema_version": "extraction-v1",
        "recording_id": recording_id,
        "speaker_id": speaker_id,
        "speaker_name": speaker_name,
        "languages": list(dict.fromkeys(language for raw in raws for language in raw["languages"])),
    }
    for collection in (
        "provenance_activities",
        "evidence_spans",
        "coreference_links",
        "conflict_sets",
        "people_mentions",
        "relationship_claims",
        "events",
        "descriptions",
        "stories",
        "unresolved_questions",
    ):
        combined[collection] = [item for raw in raws for item in raw[collection]]

    evidence, evidence_mapping, duplicate_evidence = _deduplicate_evidence(
        combined["evidence_spans"]
    )
    combined["evidence_spans"] = evidence
    remapped_combined = _replace_ids(combined, evidence_mapping)
    assert isinstance(remapped_combined, dict)
    combined = remapped_combined

    duplicate_counts: dict[str, int] = {}
    for collection in (
        "relationship_claims",
        "events",
        "descriptions",
        "stories",
        "unresolved_questions",
    ):
        accepted, mapping, duplicate_count = _deduplicate_collection(
            combined[collection], collection
        )
        combined[collection] = accepted
        remapped_combined = _replace_ids(combined, mapping)
        assert isinstance(remapped_combined, dict)
        combined = remapped_combined
        duplicate_counts[collection] = duplicate_count

    result = ExtractionResult.model_validate(combined)
    object_count = sum(
        len(items)
        for items in (
            result.people_mentions,
            result.relationship_claims,
            result.events,
            result.descriptions,
            result.stories,
            result.unresolved_questions,
        )
    )
    deduplicated = duplicate_people + duplicate_evidence + sum(duplicate_counts.values())
    return result, MergeReport(
        accepted=object_count,
        deduplicated=deduplicated,
        conflicted=len(result.conflict_sets),
        quarantined=0,
        remapped=remapped_count,
        review_required=review_required + len(result.conflict_sets),
        duplicate_people=duplicate_people,
        duplicate_relationships=duplicate_counts["relationship_claims"],
        duplicate_events=duplicate_counts["events"],
        duplicate_stories=duplicate_counts["stories"],
    )
