"""Reusable factories for the PR-03 authorization security model.

Existing family route tests authenticate with a shared CORE_API_KEY and create
no users, families or memberships. PR-03B-SWITCH has to convert them to real
principals with real membership rows, and that conversion should be a fixture
swap rather than a new test architecture. Everything those tests will need lives
here.

Route authorization tests inject a fake verifier: the subject under test is the
policy, and real RSA signing per test would obscure it while adding seconds.
Genuine signature behaviour is covered end to end in test_auth_verifier.py.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from mura.identity.auth import Principal, VerifiedIdentity
from mura.identity.policy import FamilyRole
from mura.storage.archive import ArchiveConflictRow, ArchivePersonRow
from mura.storage.database import (
    Database,
    PipelineResultRow,
    ProcessingJobRow,
    RecordingRepository,
)
from mura.storage.identity import FamilyMembershipRow, FamilyRow, IdentityRepository
from mura.storage.profile_models import MaterializedPersonProfileRow

ISSUER = "https://issuer.test/"

#: A real RIFF/WAVE header; uploads are content-validated since PR-02C.
WAV_BYTES = b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 32


@dataclass(frozen=True)
class TestIdentity:
    """A verified identity plus the internal user it resolves to."""

    #: Not a test class despite the name; keeps pytest from trying to collect it.
    __test__ = False

    identity: VerifiedIdentity
    principal: Principal

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def headers(self) -> dict[str, str]:
        """Any non-empty bearer works with the injected verifier."""

        return {"Authorization": f"Bearer test-token-{self.identity.subject}"}


class FakePrincipalVerifier:
    """Maps opaque test bearer tokens to identities without signing anything."""

    def __init__(self) -> None:
        self._by_token: dict[str, VerifiedIdentity] = {}

    def register(self, identity: VerifiedIdentity) -> str:
        token = f"test-token-{identity.subject}"
        self._by_token[token] = identity
        return token

    def verify(self, credentials: str | None) -> VerifiedIdentity:
        from mura.identity.auth import AuthenticationError, bearer_credentials

        token = bearer_credentials(credentials)
        identity = self._by_token.get(token)
        if identity is None:
            raise AuthenticationError("token could not be verified")
        return identity


def create_test_user(
    repository: IdentityRepository,
    *,
    subject: str,
    email: str | None = None,
    display_name: str | None = None,
    verifier: FakePrincipalVerifier | None = None,
) -> TestIdentity:
    identity = VerifiedIdentity(
        issuer=ISSUER, subject=subject, email=email, display_name=display_name
    )
    if verifier is not None:
        verifier.register(identity)
    return TestIdentity(identity=identity, principal=repository.resolve_principal(identity))


def create_test_family(repository: IdentityRepository, *, name: str, owner: TestIdentity) -> str:
    return repository.create_family(name=name, owner_user_id=owner.user_id).family_id


def create_family_with_id(
    database: Database, *, family_id: str, name: str = "Отбасы", owner: TestIdentity | None = None
) -> str:
    """Create a family under a caller-chosen id.

    Historical suites seed archive rows against fixed family ids like
    ``family_a``. Those ids are the point of their cross-family assertions, so
    the identity rows are created to match rather than the other way round.
    """

    with database.session_factory.begin() as session:
        session.add(
            FamilyRow(
                family_id=family_id,
                name=name,
                created_by_user_id=owner.user_id if owner is not None else None,
            )
        )
    if owner is not None:
        create_membership(database, family_id=family_id, user=owner, role=FamilyRole.OWNER)
    return family_id


def create_membership(
    database: Database, *, family_id: str, user: TestIdentity, role: FamilyRole
) -> None:
    with database.session_factory.begin() as session:
        session.add(
            FamilyMembershipRow(
                membership_id=f"membership_{uuid.uuid4().hex}",
                family_id=family_id,
                user_id=user.user_id,
                role=role.value,
            )
        )


# ------------------------------------------------------------------ resources


def seed_recording_for_family(
    database: Database,
    *,
    family_id: str,
    recording_id: str,
    job_id: str,
    with_result: bool = True,
) -> None:
    RecordingRepository(database).create_recording_and_job(
        recording_id=recording_id,
        job_id=job_id,
        family_id=family_id,
        speaker_id=f"narrator_{recording_id}",
        speaker_name="Айсұлу",
        original_filename="memory.wav",
        content_type="audio/wav",
        audio_path=f"family/{family_id}/recordings/{recording_id}/original.wav",
        storage_key=f"family/{family_id}/recordings/{recording_id}/original.wav",
        storage_backend="local",
        audio_language="auto",
        output_language="same_as_transcript",
    )
    if with_result:
        with database.session_factory.begin() as session:
            session.add(
                PipelineResultRow(
                    recording_id=recording_id, payload=_pipeline_payload(recording_id)
                )
            )


def seed_profile_for_family(
    database: Database, *, family_id: str, person_id: str, name: str = "Сапар"
) -> None:
    with database.session_factory.begin() as session:
        session.add(
            ArchivePersonRow(
                person_id=person_id,
                family_id=family_id,
                canonical_name=name,
                normalized_name=name.lower(),
            )
        )


def seed_materialized_profile_for_family(
    database: Database, *, family_id: str, person_id: str, name: str = "Сапар"
) -> None:
    """What the profile routes actually read: the materialized projection."""

    with database.session_factory.begin() as session:
        session.add(
            MaterializedPersonProfileRow(
                person_id=person_id,
                family_id=family_id,
                canonical_name=name,
                profile_payload={
                    "person_id": person_id,
                    "family_id": family_id,
                    "canonical_name": name,
                    "category": "family_member",
                    "birth_date": None,
                    "death_date": None,
                    "aliases": [],
                    "professions": [],
                    "locations": [],
                    "education": [],
                    "descriptions": [],
                    "events": [],
                    "source_claim_ids": [],
                },
                source_claim_ids=[],
            )
        )


def seed_conflict_for_family(
    database: Database,
    *,
    family_id: str,
    conflict_id: str,
    conflict_type: str = "attribute_disagreement",
) -> None:
    with database.session_factory.begin() as session:
        session.add(
            ArchiveConflictRow(
                conflict_id=conflict_id,
                family_id=family_id,
                conflict_type=conflict_type,
                status="open",
                detected_by="deterministic",
                claim_ids=[],
                rationale="seeded for authorization tests",
            )
        )


def job_row(database: Database, job_id: str) -> ProcessingJobRow | None:
    with database.session_factory() as session:
        return session.get(ProcessingJobRow, job_id)


def upload_payload() -> dict[str, Any]:
    return {
        "files": {"file": ("memory.wav", io.BytesIO(WAV_BYTES), "audio/wav")},
        "data": {"speaker_name": "Айсұлу"},
    }


def _pipeline_payload(recording_id: str) -> dict[str, Any]:
    return {
        "transcript": {
            "recording_id": recording_id,
            "duration_seconds": 12.0,
            "full_text": "Менің атам Сапар.",
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start": 0.0,
                    "end": 12.0,
                    "text": "Менің атам Сапар.",
                }
            ],
            "asr_model": "gigaam",
            "asr_revision": "large_ctc",
            "chunker_version": "v1",
        },
        "cleaned_transcript": {
            "readable_segments": [{"segment_id": "seg_001", "text": "Менің атам Сапар."}],
            "full_readable_text": "Менің атам Сапар.",
        },
        "extraction": {
            "recording_id": recording_id,
            "speaker_id": f"narrator_{recording_id}",
            "speaker_name": "Айсұлу",
            "languages": ["kk"],
        },
        "resolutions": [],
        "processing": {"total_seconds": 1.0},
    }


# --------------------------------------------------------------- app wiring


@dataclass
class AuthorizedApp:
    """An app wired for authorization tests, plus the world it operates on."""

    app: FastAPI
    database: Database
    identity: IdentityRepository
    verifier: FakePrincipalVerifier
    tmp_path: Path

    def user(self, subject: str, **kwargs: Any) -> TestIdentity:
        return create_test_user(self.identity, subject=subject, verifier=self.verifier, **kwargs)


def utc_now() -> datetime:
    return datetime.now(UTC)
