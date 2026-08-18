from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from pydantic import Field
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from mura.domain.models import EvidenceClass, StrictModel
from mura.storage.archive import ArchiveClaimRow
from mura.storage.database import JSON_VALUE, Base, utcnow

ATTRIBUTE_OBJECT_TYPE = "attribute"

AUTO_MATERIALIZABLE_CLASSES = {
    EvidenceClass.A_EXPLICIT.value,
    EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT.value,
    EvidenceClass.C_SPEAKER_ANCHORED.value,
}


class MaterializedPersonProfileRow(Base):
    __tablename__ = "materialized_person_profiles"

    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), index=True)
    canonical_name: Mapped[str] = mapped_column(String(256))
    profile_payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    source_claim_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class MaterializedAttributeView(StrictModel):
    attribute_type: str
    value: str
    normalized_value: str
    source_claim_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersonProfileView(StrictModel):
    person_id: str
    family_id: str
    canonical_name: str
    category: str
    birth_date: MaterializedAttributeView | None = None
    death_date: MaterializedAttributeView | None = None
    aliases: list[MaterializedAttributeView] = Field(default_factory=list)
    professions: list[MaterializedAttributeView] = Field(default_factory=list)
    locations: list[MaterializedAttributeView] = Field(default_factory=list)
    education: list[MaterializedAttributeView] = Field(default_factory=list)
    descriptions: list[MaterializedAttributeView] = Field(default_factory=list)
    events: list[MaterializedAttributeView] = Field(default_factory=list)
    source_claim_ids: list[str] = Field(default_factory=list)
    updated_at: datetime


class GenericProjectionReport(StrictModel):
    projected_claims: int = Field(ge=0)
    open_conflicts: int = Field(ge=0)
    materialized_profiles: int = Field(ge=0)


class ProfileNotFoundError(LookupError):
    pass


def normalize_attribute_value(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.replace("_", " ").split())


def generic_claim_is_grounded(claim: ArchiveClaimRow) -> bool:
    return (
        claim.object_type == ATTRIBUTE_OBJECT_TYPE
        and claim.subject_person_id is not None
        and claim.evidence_class in AUTO_MATERIALIZABLE_CLASSES
        and bool(claim.evidence_ids)
    )


def generic_claim_value(claim: ArchiveClaimRow) -> str:
    return str(claim.payload.get("normalized_value", ""))
