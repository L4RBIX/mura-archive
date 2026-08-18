from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mura.domain.models import FamilyEvent, NameVariantType, PipelineResult
from mura.storage.archive import (
    ArchiveClaimRow,
    ArchiveConflictRow,
    ArchivePersonRow,
    _json_payload,
    _mapped_people,
    _stable_id,
)
from mura.storage.conflict_resolution import ConflictAction, ConflictResolutionService
from mura.storage.database import RecordingRow, utcnow
from mura.storage.profile_models import (
    ATTRIBUTE_OBJECT_TYPE,
    GenericProjectionReport,
    MaterializedPersonProfileRow,
    generic_claim_is_grounded,
    generic_claim_value,
    normalize_attribute_value,
)

_PROFILE_ALIAS_VARIANTS = {
    NameVariantType.EXPLICIT_ALIAS,
    NameVariantType.NICKNAME,
    NameVariantType.DIMINUTIVE,
    NameVariantType.TRANSLITERATION,
    NameVariantType.SCRIPT_VARIANT,
}
_BIRTH_EVENT_TYPES = {
    "birth",
    "born",
    "birth event",
    "рождение",
    "родился",
    "родилась",
    "туған",
    "дүниеге келу",
}
_DEATH_EVENT_TYPES = {
    "death",
    "died",
    "deceased",
    "смерть",
    "умер",
    "умерла",
    "қайтыс болу",
    "қайтыс болды",
}
_PROFESSION_EVENT_TYPES = {
    "profession",
    "occupation",
    "career",
    "work",
    "job",
    "профессия",
    "работа",
    "карьера",
    "мамандық",
    "жұмыс",
}
_EDUCATION_EVENT_TYPES = {
    "education",
    "school",
    "university",
    "study",
    "учёба",
    "учеба",
    "школа",
    "университет",
    "білім",
    "мектеп",
    "университетте оқу",
}


def _source_claims_for_recording(
    session: Session,
    *,
    recording_id: str,
) -> dict[tuple[str, str], ArchiveClaimRow]:
    rows = list(
        session.scalars(select(ArchiveClaimRow).where(ArchiveClaimRow.recording_id == recording_id))
    )
    return {(row.object_type, row.source_object_id): row for row in rows}


def _insert_attribute_claim(
    session: Session,
    *,
    recording: RecordingRow,
    source_claim: ArchiveClaimRow | None,
    source_object_id: str,
    subject_person_id: str | None,
    attribute_type: str,
    value: str,
    evidence_ids: list[str],
    evidence_class: str,
    verification_status: str,
    assertion_mode: str | None,
    metadata: dict[str, Any],
) -> int:
    normalized_value = normalize_attribute_value(value)
    if not normalized_value:
        return 0
    payload = {
        "attribute_type": attribute_type,
        "value": value,
        "normalized_value": normalized_value,
        "source_object_id": source_object_id,
        "metadata": metadata,
    }
    claim_id = _stable_id(
        "claim",
        recording.recording_id,
        ATTRIBUTE_OBJECT_TYPE,
        source_object_id,
        subject_person_id or "unresolved",
        attribute_type,
        normalized_value,
        _json_payload(metadata),
    )
    if session.get(ArchiveClaimRow, claim_id) is not None:
        return 0
    session.add(
        ArchiveClaimRow(
            claim_id=claim_id,
            family_id=recording.family_id,
            recording_id=recording.recording_id,
            object_type=ATTRIBUTE_OBJECT_TYPE,
            source_object_id=source_object_id,
            predicate=attribute_type,
            subject_person_id=subject_person_id,
            object_person_id=None,
            payload=payload,
            evidence_ids=evidence_ids,
            evidence_class=evidence_class,
            verification_status=verification_status,
            assertion_mode=assertion_mode,
            status="active" if subject_person_id is not None else "unresolved",
            derived_from_claim_ids=[source_claim.claim_id] if source_claim is not None else [],
        )
    )
    return 1


def _project_aliases(
    session: Session,
    *,
    recording: RecordingRow,
    result: PipelineResult,
    mapped_people: dict[str, str],
    source_claims: dict[tuple[str, str], ArchiveClaimRow],
) -> int:
    projected = 0
    for mention in result.extraction.people_mentions:
        person_id = mapped_people.get(mention.mention_id)
        source_claim = source_claims.get(("person_mention", mention.mention_id))
        for variant in mention.name_variants:
            if variant.variant_type not in _PROFILE_ALIAS_VARIANTS:
                continue
            projected += _insert_attribute_claim(
                session,
                recording=recording,
                source_claim=source_claim,
                source_object_id=f"{mention.mention_id}:{variant.variant_id}",
                subject_person_id=person_id,
                attribute_type="alias",
                value=variant.surface,
                evidence_ids=list(variant.evidence_ids or mention.evidence_ids),
                evidence_class=mention.evidence_class.value,
                verification_status=variant.verification_status.value,
                assertion_mode=mention.assertion_mode.value,
                metadata={
                    "variant_type": variant.variant_type.value,
                    "language": variant.language,
                    "script": variant.script,
                },
            )
    return projected


def _project_descriptions(
    session: Session,
    *,
    recording: RecordingRow,
    result: PipelineResult,
    mapped_people: dict[str, str],
    source_claims: dict[tuple[str, str], ArchiveClaimRow],
) -> int:
    projected = 0
    for description in result.extraction.descriptions:
        projected += _insert_attribute_claim(
            session,
            recording=recording,
            source_claim=source_claims.get(("description", description.description_id)),
            source_object_id=description.description_id,
            subject_person_id=mapped_people.get(description.person_mention_id),
            attribute_type="description",
            value=description.description,
            evidence_ids=list(description.evidence_ids),
            evidence_class=description.evidence_class.value,
            verification_status=description.verification_status.value,
            assertion_mode=description.assertion_mode.value,
            metadata={"perspective": description.perspective},
        )
    return projected


def _event_facets(event: FamilyEvent) -> list[tuple[str, str, dict[str, Any]]]:
    event_type = normalize_attribute_value(event.event_type)
    date_payload = event.date.model_dump(mode="json") if event.date is not None else None
    facets: list[tuple[str, str, dict[str, Any]]] = [
        (
            "event",
            event.description or event.title,
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "title": event.title,
                "date": date_payload,
                "location": event.location,
            },
        )
    ]
    if event.location:
        facets.append(
            (
                "location",
                event.location,
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "date": date_payload,
                },
            )
        )
    if event.date is not None and event.date.value:
        metadata = {
            "event_id": event.event_id,
            "precision": event.date.precision,
            "original_expression": event.date.original_expression,
        }
        if event_type in _BIRTH_EVENT_TYPES:
            facets.append(("birth_date", event.date.value, metadata))
        elif event_type in _DEATH_EVENT_TYPES:
            facets.append(("death_date", event.date.value, metadata))
    if event_type in _PROFESSION_EVENT_TYPES:
        facets.append(
            (
                "profession",
                event.description or event.title,
                {"event_id": event.event_id, "event_type": event.event_type},
            )
        )
    if event_type in _EDUCATION_EVENT_TYPES:
        facets.append(
            (
                "education",
                event.description or event.title,
                {"event_id": event.event_id, "event_type": event.event_type},
            )
        )
    return facets


def _project_events(
    session: Session,
    *,
    recording: RecordingRow,
    result: PipelineResult,
    mapped_people: dict[str, str],
    source_claims: dict[tuple[str, str], ArchiveClaimRow],
) -> int:
    projected = 0
    for event in result.extraction.events:
        source_claim = source_claims.get(("event", event.event_id))
        for mention_id in event.participant_mention_ids:
            for attribute_type, value, metadata in _event_facets(event):
                projected += _insert_attribute_claim(
                    session,
                    recording=recording,
                    source_claim=source_claim,
                    source_object_id=f"{event.event_id}:{mention_id}:{attribute_type}",
                    subject_person_id=mapped_people.get(mention_id),
                    attribute_type=attribute_type,
                    value=value,
                    evidence_ids=list(event.evidence_ids),
                    evidence_class=event.evidence_class.value,
                    verification_status=event.verification_status.value,
                    assertion_mode=event.assertion_mode.value,
                    metadata=metadata,
                )
    return projected


def _generic_claims(session: Session, *, family_id: str) -> list[ArchiveClaimRow]:
    return list(
        session.scalars(
            select(ArchiveClaimRow).where(
                ArchiveClaimRow.family_id == family_id,
                ArchiveClaimRow.object_type == ATTRIBUTE_OBJECT_TYPE,
            )
        )
    )


def _conflict_groups(
    claims: list[ArchiveClaimRow],
) -> dict[tuple[str, ...], tuple[str, list[ArchiveClaimRow], str]]:
    groups: dict[tuple[str, ...], tuple[str, list[ArchiveClaimRow], str]] = {}
    temporal: dict[tuple[str, str], list[ArchiveClaimRow]] = defaultdict(list)
    aliases: dict[str, list[ArchiveClaimRow]] = defaultdict(list)
    for claim in claims:
        if not generic_claim_is_grounded(claim):
            continue
        if claim.predicate in {"birth_date", "death_date"}:
            temporal[(claim.subject_person_id or "", claim.predicate)].append(claim)
        elif claim.predicate == "alias" and generic_claim_value(claim):
            aliases[generic_claim_value(claim)].append(claim)

    for (person_id, predicate), candidates in temporal.items():
        if len({generic_claim_value(candidate) for candidate in candidates}) <= 1:
            continue
        groups[("temporal", person_id, predicate)] = (
            "temporal",
            candidates,
            f"grounded {predicate} claims disagree for archive person {person_id}",
        )
    for normalized_alias, candidates in aliases.items():
        if len({candidate.subject_person_id for candidate in candidates}) <= 1:
            continue
        groups[("identity", "alias", normalized_alias)] = (
            "identity",
            candidates,
            f"the same grounded alias is assigned to multiple people: {normalized_alias}",
        )
    return groups


def _upsert_conflict(
    session: Session,
    *,
    family_id: str,
    key: tuple[str, ...],
    conflict_type: str,
    candidates: list[ArchiveClaimRow],
    rationale: str,
) -> ArchiveConflictRow:
    conflict_id = _stable_id("conflict", family_id, *key)
    claim_ids = sorted(candidate.claim_id for candidate in candidates)
    conflict = session.get(ArchiveConflictRow, conflict_id)
    if conflict is None:
        conflict = ArchiveConflictRow(
            conflict_id=conflict_id,
            family_id=family_id,
            conflict_type=conflict_type,
            status="open",
            detected_by="deterministic",
            claim_ids=claim_ids,
            rationale=rationale,
        )
        session.add(conflict)
        session.flush()
    elif set(conflict.claim_ids) != set(claim_ids):
        previous_status = conflict.status
        previous_claim_ids = list(conflict.claim_ids)
        conflict.claim_ids = claim_ids
        conflict.status = "open"
        conflict.preferred_claim_id = None
        conflict.resolution_note = None
        conflict.updated_at = utcnow()
        ConflictResolutionService._append_decision(
            session,
            conflict=conflict,
            action=ConflictAction.AUTO_REOPEN,
            previous_status=previous_status,
            resulting_status="open",
            reviewer_reference="system:archive-ingestion",
            note="conflict reopened because its competing claim set changed",
            metadata_payload={
                "previous_claim_ids": previous_claim_ids,
                "current_claim_ids": claim_ids,
            },
        )
    elif conflict.status == "resolved" and conflict.preferred_claim_id not in claim_ids:
        previous_status = conflict.status
        conflict.status = "open"
        conflict.preferred_claim_id = None
        conflict.resolution_note = None
        conflict.updated_at = utcnow()
        ConflictResolutionService._append_decision(
            session,
            conflict=conflict,
            action=ConflictAction.AUTO_REOPEN,
            previous_status=previous_status,
            resulting_status="open",
            reviewer_reference="system:archive-ingestion",
            note="conflict reopened because the preferred claim is unavailable",
        )
    ConflictResolutionService._apply_conflict_state(session, conflict=conflict)
    return conflict


def reconcile_generic_conflicts(session: Session, *, family_id: str) -> int:
    claims = _generic_claims(session, family_id=family_id)
    for claim in claims:
        claim.status = "active" if claim.subject_person_id is not None else "unresolved"
    conflicts = [
        _upsert_conflict(
            session,
            family_id=family_id,
            key=key,
            conflict_type=conflict_type,
            candidates=candidates,
            rationale=rationale,
        )
        for key, (conflict_type, candidates, rationale) in _conflict_groups(claims).items()
    ]
    return sum(conflict.status == "open" for conflict in conflicts)


def _first_facet(
    facets: dict[str, list[dict[str, Any]]],
    predicate: str,
) -> dict[str, Any] | None:
    entries = facets.get(predicate, [])
    return entries[0] if entries else None


def rebuild_materialized_profiles(session: Session, *, family_id: str) -> int:
    session.execute(
        delete(MaterializedPersonProfileRow).where(
            MaterializedPersonProfileRow.family_id == family_id
        )
    )
    people = list(
        session.scalars(
            select(ArchivePersonRow)
            .where(ArchivePersonRow.family_id == family_id)
            .order_by(ArchivePersonRow.person_id)
        )
    )
    claims = [
        claim
        for claim in _generic_claims(session, family_id=family_id)
        if claim.status in {"active", "accepted"} and generic_claim_is_grounded(claim)
    ]
    by_person: dict[str, list[ArchiveClaimRow]] = defaultdict(list)
    for claim in claims:
        if claim.subject_person_id is not None:
            by_person[claim.subject_person_id].append(claim)

    for person in people:
        grouped: dict[str, dict[str, list[ArchiveClaimRow]]] = defaultdict(
            lambda: defaultdict(list)
        )
        person_claims = by_person.get(person.person_id, [])
        for claim in person_claims:
            grouped[claim.predicate][generic_claim_value(claim)].append(claim)

        facets: dict[str, list[dict[str, Any]]] = {}
        for predicate, values in grouped.items():
            entries: list[dict[str, Any]] = []
            for normalized_value, sources in values.items():
                first = sorted(sources, key=lambda item: item.created_at)[0]
                entries.append(
                    {
                        "attribute_type": predicate,
                        "value": str(first.payload.get("value", "")),
                        "normalized_value": normalized_value,
                        "source_claim_ids": sorted(source.claim_id for source in sources),
                        "metadata": dict(first.payload.get("metadata", {})),
                    }
                )
            facets[predicate] = sorted(
                entries,
                key=lambda item: (str(item["normalized_value"]), str(item["value"])),
            )

        source_claim_ids = sorted(claim.claim_id for claim in person_claims)
        profile_payload = {
            "person_id": person.person_id,
            "family_id": family_id,
            "canonical_name": person.canonical_name,
            "category": person.category,
            "birth_date": _first_facet(facets, "birth_date"),
            "death_date": _first_facet(facets, "death_date"),
            "aliases": facets.get("alias", []),
            "professions": facets.get("profession", []),
            "locations": facets.get("location", []),
            "education": facets.get("education", []),
            "descriptions": facets.get("description", []),
            "events": facets.get("event", []),
            "source_claim_ids": source_claim_ids,
        }
        session.add(
            MaterializedPersonProfileRow(
                person_id=person.person_id,
                family_id=family_id,
                canonical_name=person.canonical_name,
                profile_payload=profile_payload,
                source_claim_ids=source_claim_ids,
            )
        )
    return len(people)


def persist_generic_claims(
    session: Session,
    *,
    recording: RecordingRow,
    result: PipelineResult,
) -> GenericProjectionReport:
    mapped_people = _mapped_people(result)
    source_claims = _source_claims_for_recording(
        session,
        recording_id=recording.recording_id,
    )
    projected = _project_aliases(
        session,
        recording=recording,
        result=result,
        mapped_people=mapped_people,
        source_claims=source_claims,
    )
    projected += _project_descriptions(
        session,
        recording=recording,
        result=result,
        mapped_people=mapped_people,
        source_claims=source_claims,
    )
    projected += _project_events(
        session,
        recording=recording,
        result=result,
        mapped_people=mapped_people,
        source_claims=source_claims,
    )
    session.flush()
    conflicts = reconcile_generic_conflicts(session, family_id=recording.family_id)
    profiles = rebuild_materialized_profiles(session, family_id=recording.family_id)
    return GenericProjectionReport(
        projected_claims=projected,
        open_conflicts=conflicts,
        materialized_profiles=profiles,
    )
