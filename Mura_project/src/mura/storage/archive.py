from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any

from pydantic import Field
from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from mura.domain.models import (
    AssertionMode,
    ClaimObjectType,
    EvidenceBackedObject,
    EvidenceClass,
    FamilyEvent,
    KnownPerson,
    MentionResolution,
    NameVariantType,
    PersonCategory,
    PersonDescription,
    PersonMention,
    PipelineResult,
    RelationshipClaim,
    RelationshipType,
    ResolutionStatus,
    Story,
    StrictModel,
    UnresolvedQuestion,
    VerificationStatus,
)
from mura.entity_resolution import EntityResolutionContext, KnownPersonProfile
from mura.storage.database import JSON_VALUE, Base, Database, RecordingRow, utcnow

_AUTO_MATERIALIZABLE_CLASSES = {
    EvidenceClass.A_EXPLICIT.value,
    EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT.value,
    EvidenceClass.C_SPEAKER_ANCHORED.value,
}

_ALIAS_VARIANT_TYPES = {
    NameVariantType.EXPLICIT_ALIAS,
    NameVariantType.NICKNAME,
    NameVariantType.DIMINUTIVE,
    NameVariantType.TRANSLITERATION,
    NameVariantType.SCRIPT_VARIANT,
    NameVariantType.ASR_VARIANT,
}

_RELATION_GENERATIONS = {
    "self": 0,
    "spouse": 0,
    "husband": 0,
    "wife": 0,
    "sibling": 0,
    "brother": 0,
    "sister": 0,
    "older brother": 0,
    "younger brother": 0,
    "older sister": 0,
    "younger sister": 0,
    "parent": -1,
    "father": -1,
    "mother": -1,
    "child": 1,
    "son": 1,
    "daughter": 1,
    "grandparent": -2,
    "grandfather": -2,
    "grandmother": -2,
    "grandchild": 2,
    "grandson": 2,
    "granddaughter": 2,
    "әке": -1,
    "әкесі": -1,
    "ана": -1,
    "анасы": -1,
    "шеше": -1,
    "шешесі": -1,
    "ұл": 1,
    "ұлы": 1,
    "қыз": 1,
    "қызы": 1,
    "бала": 1,
    "баласы": 1,
    "аға": 0,
    "іні": 0,
    "әпке": 0,
    "сіңлі": 0,
    "қарындас": 0,
    "отец": -1,
    "мать": -1,
    "сын": 1,
    "дочь": 1,
    "брат": 0,
    "сестра": 0,
}


class ArchivePersonRow(Base):
    __tablename__ = "archive_people"

    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    canonical_name: Mapped[str] = mapped_column(String(256))
    normalized_name: Mapped[str] = mapped_column(String(256), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list)
    verified_aliases: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list)
    category: Mapped[str] = mapped_column(String(64), default=PersonCategory.UNKNOWN.value)
    relations_to_speakers: Mapped[dict[str, str]] = mapped_column(JSON_VALUE, default=dict)
    source_recording_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    __table_args__ = (UniqueConstraint("family_id", "person_id"),)


class ArchiveClaimRow(Base):
    __tablename__ = "archive_claims"

    claim_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    recording_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("recordings.recording_id", ondelete="CASCADE"),
        index=True,
    )
    object_type: Mapped[str] = mapped_column(String(64), index=True)
    source_object_id: Mapped[str] = mapped_column(String(128), index=True)
    predicate: Mapped[str] = mapped_column(String(128), index=True)
    subject_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    object_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list)
    evidence_class: Mapped[str] = mapped_column(String(64), index=True)
    verification_status: Mapped[str] = mapped_column(String(32), index=True)
    assertion_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    derived_from_claim_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArchiveConflictRow(Base):
    __tablename__ = "archive_conflicts"

    conflict_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    conflict_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    detected_by: Mapped[str] = mapped_column(String(32), default="deterministic")
    claim_ids: Mapped[list[str]] = mapped_column(JSON_VALUE)
    preferred_claim_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rationale: Mapped[str] = mapped_column(Text)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class FamilyGraphEdgeRow(Base):
    __tablename__ = "family_graph_edges"

    edge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    relationship_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_person_id: Mapped[str] = mapped_column(String(64), index=True)
    subject_role: Mapped[str] = mapped_column(String(64))
    object_person_id: Mapped[str] = mapped_column(String(64), index=True)
    object_role: Mapped[str] = mapped_column(String(64))
    source_claim_ids: Mapped[list[str]] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class ArchiveCorrectionRow(Base):
    __tablename__ = "archive_corrections"

    correction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    recording_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("recordings.recording_id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str | None] = mapped_column(String(256), nullable=True)
    original_value: Mapped[str] = mapped_column(Text)
    corrected_value: Mapped[str] = mapped_column(Text)
    source_segment_ids: Mapped[list[str]] = mapped_column(JSON_VALUE)
    explanation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArchiveWriteReport(StrictModel):
    schema_version: str = "archive-write-report-v1"
    people_upserted: int = Field(ge=0)
    claims_persisted: int = Field(ge=0)
    corrections_persisted: int = Field(ge=0)
    open_conflicts: int = Field(ge=0)
    graph_edges: int = Field(ge=0)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.replace("_", " ").split())


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:32]}"


def _json_payload(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
    result = list(existing)
    normalized = {_normalize(value) for value in existing}
    for value in incoming:
        key = _normalize(value)
        if key and key not in normalized:
            result.append(value)
            normalized.add(key)
    return result


def _object_identity(item: EvidenceBackedObject) -> tuple[ClaimObjectType, str]:
    for object_type, field_name in (
        (ClaimObjectType.PERSON_MENTION, "mention_id"),
        (ClaimObjectType.RELATIONSHIP, "relationship_id"),
        (ClaimObjectType.EVENT, "event_id"),
        (ClaimObjectType.DESCRIPTION, "description_id"),
        (ClaimObjectType.STORY, "story_id"),
        (ClaimObjectType.QUESTION, "question_id"),
    ):
        value = getattr(item, field_name, None)
        if isinstance(value, str) and value:
            return object_type, value
    raise ValueError(f"unsupported archive claim object {type(item).__name__}")


def _objects(result: PipelineResult) -> list[EvidenceBackedObject]:
    extraction = result.extraction
    return [
        *extraction.people_mentions,
        *extraction.relationship_claims,
        *extraction.events,
        *extraction.descriptions,
        *extraction.stories,
        *extraction.unresolved_questions,
    ]


def _predicate(item: EvidenceBackedObject) -> str:
    if isinstance(item, PersonMention):
        return "person_mention"
    if isinstance(item, RelationshipClaim):
        return item.relationship_type.value
    if isinstance(item, FamilyEvent):
        return item.event_type
    if isinstance(item, PersonDescription):
        return "description"
    if isinstance(item, Story):
        return "story"
    if isinstance(item, UnresolvedQuestion):
        return "question"
    raise ValueError(f"unsupported archive predicate for {type(item).__name__}")


def _resolution_map(result: PipelineResult) -> dict[str, MentionResolution]:
    return {resolution.mention_id: resolution for resolution in result.resolutions}


def _person_id_for_new(recording_id: str, mention_id: str) -> str:
    return _stable_id("person", recording_id, mention_id)


def _mapped_people(result: PipelineResult) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for mention in result.extraction.people_mentions:
        resolution = _resolution_map(result).get(mention.mention_id)
        if resolution is None:
            continue
        if resolution.status is ResolutionStatus.RESOLVED and resolution.person_id:
            mapped[mention.mention_id] = resolution.person_id
        elif resolution.status is ResolutionStatus.NEW_PERSON:
            mapped[mention.mention_id] = _person_id_for_new(
                result.transcript.recording_id,
                mention.mention_id,
            )
    return mapped


def _relationship_signature(row: ArchiveClaimRow) -> tuple[str, ...]:
    payload = row.payload
    relationship_type = str(payload["relationship_type"])
    subject_role = str(payload["subject_role"])
    object_role = str(payload["object_role"])
    subject_id = row.subject_person_id or ""
    object_id = row.object_person_id or ""
    if relationship_type in {RelationshipType.SPOUSE.value, RelationshipType.SIBLING.value}:
        endpoints = sorted(((subject_id, subject_role), (object_id, object_role)))
        return (
            relationship_type,
            endpoints[0][0],
            endpoints[0][1],
            endpoints[1][0],
            endpoints[1][1],
        )
    return relationship_type, subject_id, subject_role, object_id, object_role


def _relationship_state_status(row: ArchiveClaimRow) -> str:
    if row.subject_person_id is None or row.object_person_id is None:
        return "unresolved"
    state = str(row.payload.get("relationship_state", "current"))
    if (
        row.payload.get("uncertainty") is not None
        or row.assertion_mode == AssertionMode.UNCERTAIN.value
    ):
        return "unresolved"
    if state == "former":
        return "historical"
    if state == "ended":
        return "ended"
    if state == "negated":
        return "negated"
    if state == "figurative":
        return "figurative"
    if state != "current":
        return "unresolved"
    return "active"


def _relationship_claim_is_active(row: ArchiveClaimRow) -> bool:
    return _relationship_state_status(row) == "active" and row.status in {"active", "accepted"}


def _relationship_pair(row: ArchiveClaimRow) -> tuple[str, str]:
    first, second = sorted((row.subject_person_id or "", row.object_person_id or ""))
    return first, second


def _edge_values(row: ArchiveClaimRow) -> tuple[str, str, str, str, str]:
    payload = row.payload
    relationship_type = str(payload["relationship_type"])
    subject_id = row.subject_person_id or ""
    object_id = row.object_person_id or ""
    subject_role = str(payload["subject_role"])
    object_role = str(payload["object_role"])
    if relationship_type in {RelationshipType.SPOUSE.value, RelationshipType.SIBLING.value}:
        endpoints = sorted(((subject_id, subject_role), (object_id, object_role)))
        subject_id, subject_role = endpoints[0]
        object_id, object_role = endpoints[1]
    return relationship_type, subject_id, subject_role, object_id, object_role


class ArchiveRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def persist_pipeline_result(
        session: Session,
        *,
        recording: RecordingRow,
        result: PipelineResult,
    ) -> ArchiveWriteReport:
        mapped_people = _mapped_people(result)
        people_upserted = ArchiveRepository._upsert_people(
            session,
            recording=recording,
            result=result,
            mapped_people=mapped_people,
        )
        claims_persisted = ArchiveRepository._persist_claims(
            session,
            recording=recording,
            result=result,
            mapped_people=mapped_people,
        )
        corrections_persisted = ArchiveRepository._persist_corrections(
            session,
            recording=recording,
            result=result,
        )
        open_conflicts = ArchiveRepository._rebuild_relationship_conflicts(
            session,
            family_id=recording.family_id,
        )
        graph_edges = ArchiveRepository._rebuild_graph(
            session,
            family_id=recording.family_id,
        )
        return ArchiveWriteReport(
            people_upserted=people_upserted,
            claims_persisted=claims_persisted,
            corrections_persisted=corrections_persisted,
            open_conflicts=open_conflicts,
            graph_edges=graph_edges,
        )

    @staticmethod
    def _upsert_people(
        session: Session,
        *,
        recording: RecordingRow,
        result: PipelineResult,
        mapped_people: dict[str, str],
    ) -> int:
        count = 0
        for mention in result.extraction.people_mentions:
            person_id = mapped_people.get(mention.mention_id)
            if person_id is None:
                continue
            row = session.get(ArchivePersonRow, person_id)
            aliases = [*mention.aliases]
            aliases.extend(
                variant.surface
                for variant in mention.name_variants
                if variant.variant_type is not NameVariantType.PRIMARY
            )
            verified_aliases = [
                variant.surface
                for variant in mention.name_variants
                if variant.variant_type in _ALIAS_VARIANT_TYPES
                and variant.verification_status is VerificationStatus.CONFIRMED
            ]
            relation_map = dict(row.relations_to_speakers) if row is not None else {}
            if mention.relation_to_speaker:
                relation_map[recording.speaker_id] = mention.relation_to_speaker
            if row is None:
                row = ArchivePersonRow(
                    person_id=person_id,
                    family_id=recording.family_id,
                    canonical_name=mention.name,
                    normalized_name=_normalize(mention.name),
                    aliases=_merge_unique([], aliases),
                    verified_aliases=_merge_unique([], verified_aliases),
                    category=mention.category.value,
                    relations_to_speakers=relation_map,
                    source_recording_ids=[recording.recording_id],
                )
                session.add(row)
            else:
                if row.family_id != recording.family_id:
                    raise ValueError("resolved person belongs to another family archive")
                if _normalize(mention.name) != row.normalized_name:
                    aliases = [mention.name, *aliases]
                row.aliases = _merge_unique(list(row.aliases), aliases)
                row.verified_aliases = _merge_unique(
                    list(row.verified_aliases),
                    verified_aliases,
                )
                if row.category == PersonCategory.UNKNOWN.value:
                    row.category = mention.category.value
                row.relations_to_speakers = relation_map
                row.source_recording_ids = _merge_unique(
                    list(row.source_recording_ids),
                    [recording.recording_id],
                )
                row.updated_at = utcnow()
            count += 1
        return count

    @staticmethod
    def _persist_claims(
        session: Session,
        *,
        recording: RecordingRow,
        result: PipelineResult,
        mapped_people: dict[str, str],
    ) -> int:
        count = 0
        for item in _objects(result):
            object_type, source_object_id = _object_identity(item)
            payload = item.model_dump(mode="json")
            subject_person_id: str | None = None
            object_person_id: str | None = None
            status = "active"
            if isinstance(item, PersonMention):
                subject_person_id = mapped_people.get(item.mention_id)
                if subject_person_id is None:
                    status = "unresolved"
            elif isinstance(item, RelationshipClaim):
                subject_person_id = mapped_people.get(item.subject_mention_id)
                object_person_id = mapped_people.get(item.object_mention_id)
                if subject_person_id is None or object_person_id is None:
                    status = "unresolved"
                elif item.relationship_state.value == "former":
                    status = "historical"
                elif item.relationship_state.value == "ended":
                    status = "ended"
                elif item.relationship_state.value == "negated":
                    status = "negated"
                elif item.relationship_state.value == "figurative":
                    status = "figurative"
                elif item.relationship_state.value != "current" or item.uncertainty is not None:
                    status = "unresolved"
            assertion_mode = getattr(item, "assertion_mode", None)
            verification_status = getattr(
                item,
                "verification_status",
                VerificationStatus.UNREVIEWED,
            )
            derived_from = (
                list(item.provenance.derived_from_claim_ids) if item.provenance is not None else []
            )
            claim_id = _stable_id(
                "claim",
                recording.recording_id,
                object_type.value,
                source_object_id,
                _json_payload(payload),
            )
            if session.get(ArchiveClaimRow, claim_id) is not None:
                continue
            session.add(
                ArchiveClaimRow(
                    claim_id=claim_id,
                    family_id=recording.family_id,
                    recording_id=recording.recording_id,
                    object_type=object_type.value,
                    source_object_id=source_object_id,
                    predicate=_predicate(item),
                    subject_person_id=subject_person_id,
                    object_person_id=object_person_id,
                    payload=payload,
                    evidence_ids=list(item.evidence_ids),
                    evidence_class=item.evidence_class.value,
                    verification_status=verification_status.value,
                    assertion_mode=(
                        assertion_mode.value if isinstance(assertion_mode, AssertionMode) else None
                    ),
                    status=status,
                    derived_from_claim_ids=derived_from,
                )
            )
            count += 1
        return count

    @staticmethod
    def _persist_corrections(
        session: Session,
        *,
        recording: RecordingRow,
        result: PipelineResult,
    ) -> int:
        count = 0
        for correction in result.cleaned_transcript.detected_corrections:
            payload = correction.model_dump(mode="json")
            correction_id = _stable_id(
                "correction",
                recording.recording_id,
                _json_payload(payload),
            )
            if session.get(ArchiveCorrectionRow, correction_id) is not None:
                continue
            session.add(
                ArchiveCorrectionRow(
                    correction_id=correction_id,
                    family_id=recording.family_id,
                    recording_id=recording.recording_id,
                    kind=correction.kind.value,
                    subject=correction.subject,
                    original_value=correction.original_value,
                    corrected_value=correction.corrected_value,
                    source_segment_ids=list(correction.source_segment_ids),
                    explanation=correction.explanation,
                    confidence=str(correction.confidence),
                )
            )
            count += 1
        return count

    @staticmethod
    def _rebuild_relationship_conflicts(session: Session, *, family_id: str) -> int:
        session.execute(
            delete(ArchiveConflictRow).where(
                ArchiveConflictRow.family_id == family_id,
                ArchiveConflictRow.detected_by == "deterministic",
                ArchiveConflictRow.status == "open",
            )
        )
        claims = list(
            session.scalars(
                select(ArchiveClaimRow).where(
                    ArchiveClaimRow.family_id == family_id,
                    ArchiveClaimRow.object_type == ClaimObjectType.RELATIONSHIP.value,
                )
            )
        )
        for claim in claims:
            claim.status = _relationship_state_status(claim)

        eligible = [
            claim
            for claim in claims
            if _relationship_claim_is_active(claim)
            and claim.evidence_class in _AUTO_MATERIALIZABLE_CLASSES
            and claim.evidence_ids
        ]
        grouped: dict[tuple[str, str], list[ArchiveClaimRow]] = defaultdict(list)
        for claim in eligible:
            grouped[_relationship_pair(claim)].append(claim)

        conflict_count = 0
        for pair, candidates in grouped.items():
            signatures = {_relationship_signature(candidate) for candidate in candidates}
            if len(signatures) <= 1:
                continue
            claim_ids = sorted(candidate.claim_id for candidate in candidates)
            conflict_id = _stable_id("conflict", family_id, *claim_ids)
            session.add(
                ArchiveConflictRow(
                    conflict_id=conflict_id,
                    family_id=family_id,
                    conflict_type="relationship",
                    status="open",
                    detected_by="deterministic",
                    claim_ids=claim_ids,
                    rationale=(
                        "grounded relationship claims disagree for archive people "
                        f"{pair[0]} and {pair[1]}"
                    ),
                )
            )
            for candidate in candidates:
                candidate.status = "disputed"
            conflict_count += 1
        return conflict_count

    @staticmethod
    def _rebuild_graph(session: Session, *, family_id: str) -> int:
        session.execute(delete(FamilyGraphEdgeRow).where(FamilyGraphEdgeRow.family_id == family_id))
        claims = list(
            session.scalars(
                select(ArchiveClaimRow).where(
                    ArchiveClaimRow.family_id == family_id,
                    ArchiveClaimRow.object_type == ClaimObjectType.RELATIONSHIP.value,
                )
            )
        )
        eligible = [
            claim
            for claim in claims
            if _relationship_claim_is_active(claim)
            and claim.evidence_class in _AUTO_MATERIALIZABLE_CLASSES
            and claim.evidence_ids
            and claim.subject_person_id is not None
            and claim.object_person_id is not None
            and claim.subject_person_id != claim.object_person_id
        ]
        grouped: dict[tuple[str, str, str, str, str], list[ArchiveClaimRow]] = defaultdict(list)
        for claim in eligible:
            grouped[_edge_values(claim)].append(claim)

        for values, sources in grouped.items():
            relationship_type, subject_id, subject_role, object_id, object_role = values
            edge_id = _stable_id("edge", family_id, *values)
            session.add(
                FamilyGraphEdgeRow(
                    edge_id=edge_id,
                    family_id=family_id,
                    relationship_type=relationship_type,
                    subject_person_id=subject_id,
                    subject_role=subject_role,
                    object_person_id=object_id,
                    object_role=object_role,
                    source_claim_ids=sorted(source.claim_id for source in sources),
                )
            )
        return len(grouped)

    def build_resolution_context(
        self,
        *,
        family_id: str,
        speaker_id: str,
    ) -> EntityResolutionContext:
        with self.database.session_factory() as session:
            people = list(
                session.scalars(
                    select(ArchivePersonRow)
                    .where(ArchivePersonRow.family_id == family_id)
                    .order_by(ArchivePersonRow.person_id)
                )
            )
            edges = list(
                session.scalars(
                    select(FamilyGraphEdgeRow).where(FamilyGraphEdgeRow.family_id == family_id)
                )
            )

        parents: dict[str, set[str]] = defaultdict(set)
        children: dict[str, set[str]] = defaultdict(set)
        spouses: dict[str, set[str]] = defaultdict(set)
        siblings: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            if edge.relationship_type == RelationshipType.PARENT_CHILD.value:
                parents[edge.object_person_id].add(edge.subject_person_id)
                children[edge.subject_person_id].add(edge.object_person_id)
            elif edge.relationship_type == RelationshipType.SPOUSE.value:
                spouses[edge.subject_person_id].add(edge.object_person_id)
                spouses[edge.object_person_id].add(edge.subject_person_id)
            elif edge.relationship_type == RelationshipType.SIBLING.value:
                siblings[edge.subject_person_id].add(edge.object_person_id)
                siblings[edge.object_person_id].add(edge.subject_person_id)

        profiles: list[KnownPersonProfile] = []
        for row in people:
            relation = row.relations_to_speakers.get(speaker_id)
            generation = _RELATION_GENERATIONS.get(_normalize(relation)) if relation else None
            profiles.append(
                KnownPersonProfile(
                    family_id=family_id,
                    person=KnownPerson(
                        person_id=row.person_id,
                        canonical_name=row.canonical_name,
                        aliases=list(row.aliases),
                        category=PersonCategory(row.category),
                        relation_to_speaker=relation,
                    ),
                    verified_aliases=list(row.verified_aliases),
                    generation_relative_to_speaker=generation,
                    parent_person_ids=sorted(parents[row.person_id]),
                    child_person_ids=sorted(children[row.person_id]),
                    spouse_person_ids=sorted(spouses[row.person_id]),
                    sibling_person_ids=sorted(siblings[row.person_id]),
                    source_recording_ids=list(row.source_recording_ids),
                )
            )
        return EntityResolutionContext(
            family_id=family_id,
            speaker_id=speaker_id,
            profiles=profiles,
        )

    def list_people(self, family_id: str) -> list[ArchivePersonRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(ArchivePersonRow)
                    .where(ArchivePersonRow.family_id == family_id)
                    .order_by(ArchivePersonRow.person_id)
                )
            )

    def list_claims(self, family_id: str) -> list[ArchiveClaimRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(ArchiveClaimRow)
                    .where(ArchiveClaimRow.family_id == family_id)
                    .order_by(ArchiveClaimRow.created_at, ArchiveClaimRow.claim_id)
                )
            )

    def list_conflicts(self, family_id: str) -> list[ArchiveConflictRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(ArchiveConflictRow)
                    .where(ArchiveConflictRow.family_id == family_id)
                    .order_by(ArchiveConflictRow.created_at, ArchiveConflictRow.conflict_id)
                )
            )

    def list_graph_edges(self, family_id: str) -> list[FamilyGraphEdgeRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(FamilyGraphEdgeRow)
                    .where(FamilyGraphEdgeRow.family_id == family_id)
                    .order_by(FamilyGraphEdgeRow.edge_id)
                )
            )

    def list_corrections(self, family_id: str) -> list[ArchiveCorrectionRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(ArchiveCorrectionRow)
                    .where(ArchiveCorrectionRow.family_id == family_id)
                    .order_by(ArchiveCorrectionRow.created_at, ArchiveCorrectionRow.correction_id)
                )
            )
