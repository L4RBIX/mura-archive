from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from apps.api.main import create_app, get_auth_verifier, get_runtime, get_settings
from mura.config import CoreSettings
from mura.identity.policy import FamilyRole
from mura.storage.archive import ArchiveClaimRow, ArchiveConflictRow
from mura.storage.database import Database, RecordingRow
from mura.storage.identity import IdentityRepository
from tests.authz_factories import (
    FakePrincipalVerifier,
    create_family_with_id,
    create_membership,
    create_test_user,
)

DEEPSEEK_KEY = "sk-" + "d" * 40
REGISTRATION_TOKEN = "r" * 40
ASR_TOKEN = "a" * 40
CORE_TOKEN = "c" * 40


def _settings() -> CoreSettings:
    return CoreSettings.model_validate(
        {
            "DEEPSEEK_API_KEY": DEEPSEEK_KEY,
            "CORE_API_KEY": CORE_TOKEN,
            "WORKER_REGISTRATION_TOKEN": REGISTRATION_TOKEN,
            "KAGGLE_ASR_API_KEY": ASR_TOKEN,
            "OPERATIONS_API_KEY": "o" * 40,
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        }
    )


def _seed_database() -> Database:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    with database.session_factory.begin() as session:
        session.add_all(
            [
                RecordingRow(
                    recording_id="rec_parent",
                    family_id="family_1",
                    speaker_id="speaker_1",
                    speaker_name="Күләш",
                    original_filename="parent.wav",
                    content_type="audio/wav",
                    audio_path="/tmp/parent.wav",
                ),
                RecordingRow(
                    recording_id="rec_spouse",
                    family_id="family_1",
                    speaker_id="speaker_1",
                    speaker_name="Күләш",
                    original_filename="spouse.wav",
                    content_type="audio/wav",
                    audio_path="/tmp/spouse.wav",
                ),
            ]
        )
        session.add_all(
            [
                ArchiveClaimRow(
                    claim_id="claim_parent",
                    family_id="family_1",
                    recording_id="rec_parent",
                    object_type="relationship",
                    source_object_id="relationship_parent",
                    predicate="parent_child",
                    subject_person_id="person_erlan",
                    object_person_id="person_nurlan",
                    payload={
                        "relationship_type": "parent_child",
                        "subject_role": "parent",
                        "object_role": "child",
                    },
                    evidence_ids=["evidence_parent"],
                    evidence_class="A_explicit",
                    verification_status="unreviewed",
                    assertion_mode="explicit",
                    status="disputed",
                    derived_from_claim_ids=[],
                ),
                ArchiveClaimRow(
                    claim_id="claim_spouse",
                    family_id="family_1",
                    recording_id="rec_spouse",
                    object_type="relationship",
                    source_object_id="relationship_spouse",
                    predicate="spouse",
                    subject_person_id="person_erlan",
                    object_person_id="person_nurlan",
                    payload={
                        "relationship_type": "spouse",
                        "subject_role": "spouse",
                        "object_role": "spouse",
                    },
                    evidence_ids=["evidence_spouse"],
                    evidence_class="A_explicit",
                    verification_status="unreviewed",
                    assertion_mode="explicit",
                    status="disputed",
                    derived_from_claim_ids=[],
                ),
            ]
        )
        session.add(
            ArchiveConflictRow(
                conflict_id="conflict_api",
                family_id="family_1",
                conflict_type="relationship",
                status="open",
                detected_by="deterministic",
                claim_ids=["claim_parent", "claim_spouse"],
                rationale="fixture disagreement",
            )
        )
    return database


def test_conflict_routes_require_a_member_and_preserve_family_scope() -> None:
    """Conflict review is family data: an editor of family 1 reaches it, a
    service token does not, and family 2 membership does not reach family 1's
    conflict even though the id is known."""

    database = _seed_database()
    settings = _settings()
    identity = IdentityRepository(database)
    verifier = FakePrincipalVerifier()
    editor = create_test_user(identity, subject="conflict-editor", verifier=verifier)
    create_family_with_id(database, family_id="family_1", name="Family 1")
    create_membership(database, family_id="family_1", user=editor, role=FamilyRole.EDITOR)
    create_family_with_id(database, family_id="family_2", name="Family 2")
    create_membership(database, family_id="family_2", user=editor, role=FamilyRole.EDITOR)

    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_runtime] = lambda: SimpleNamespace(database=database)
    application.dependency_overrides[get_auth_verifier] = lambda: verifier
    client = TestClient(application, raise_server_exceptions=False)
    headers = editor.headers

    unauthorized = client.get("/v1/families/family_1/conflicts")
    assert unauthorized.status_code == 401

    service_token = client.get(
        "/v1/families/family_1/conflicts",
        headers={"Authorization": f"Bearer {CORE_TOKEN}"},
    )
    assert service_token.status_code == 401

    listed = client.get("/v1/families/family_1/conflicts", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["conflict_id"] == "conflict_api"
    assert listed.json()[0]["status"] == "open"

    hidden = client.get("/v1/families/family_2/conflicts/conflict_api", headers=headers)
    assert hidden.status_code == 404
    assert "conflict_api" not in hidden.text

    resolved = client.post(
        "/v1/families/family_1/conflicts/conflict_api/resolve",
        headers=headers,
        json={
            "preferred_claim_id": "claim_parent",
            "reviewer_reference": "reviewer:api-test",
            "note": "Family reviewer confirmed the parent relationship.",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["conflict"]["status"] == "resolved"
    assert resolved.json()["conflict"]["preferred_claim_id"] == "claim_parent"
    assert resolved.json()["graph_edges"] == 1
    assert resolved.json()["conflict"]["decisions"][0]["action"] == "resolve"

    reopened = client.post(
        "/v1/families/family_1/conflicts/conflict_api/reopen",
        headers=headers,
        json={
            "reviewer_reference": "reviewer:api-test",
            "note": "Reopen after receiving new testimony.",
        },
    )
    assert reopened.status_code == 200
    assert reopened.json()["conflict"]["status"] == "open"
    assert reopened.json()["graph_edges"] == 0
