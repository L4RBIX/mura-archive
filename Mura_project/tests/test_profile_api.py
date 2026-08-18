from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from apps.api.main import create_app, get_auth_verifier, get_runtime, get_settings
from mura.config import CoreSettings
from mura.identity.policy import FamilyRole
from mura.storage.database import Database
from mura.storage.identity import IdentityRepository
from mura.storage.profile_models import MaterializedPersonProfileRow
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
        session.add(
            MaterializedPersonProfileRow(
                person_id="person_erlan",
                family_id="family_1",
                canonical_name="Ерлан",
                profile_payload={
                    "person_id": "person_erlan",
                    "family_id": "family_1",
                    "canonical_name": "Ерлан",
                    "category": "family_member",
                    "birth_date": {
                        "attribute_type": "birth_date",
                        "value": "1978",
                        "normalized_value": "1978",
                        "source_claim_ids": ["claim_birth"],
                        "metadata": {"precision": "year"},
                    },
                    "death_date": None,
                    "aliases": [],
                    "professions": [],
                    "locations": [],
                    "education": [],
                    "descriptions": [],
                    "events": [],
                    "source_claim_ids": ["claim_birth"],
                },
                source_claim_ids=["claim_birth"],
            )
        )
    return database


def test_profile_routes_require_a_member_and_preserve_family_scope() -> None:
    """Reading the archive needs a family member, not a service token.

    The caller is a viewer of family 1 and a member of family 2, so the final
    assertion isolates resource integrity: membership in the family named in the
    path still does not reach a person belonging to a different family.
    """

    database = _seed_database()
    settings = _settings()
    identity = IdentityRepository(database)
    verifier = FakePrincipalVerifier()
    viewer = create_test_user(identity, subject="profile-viewer", verifier=verifier)
    create_family_with_id(database, family_id="family_1", name="Family 1")
    create_membership(database, family_id="family_1", user=viewer, role=FamilyRole.VIEWER)
    create_family_with_id(database, family_id="family_2", name="Family 2")
    create_membership(database, family_id="family_2", user=viewer, role=FamilyRole.VIEWER)

    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_runtime] = lambda: SimpleNamespace(database=database)
    application.dependency_overrides[get_auth_verifier] = lambda: verifier
    client = TestClient(application, raise_server_exceptions=False)
    headers = viewer.headers

    unauthorized = client.get("/v1/families/family_1/profiles")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "authentication_required"

    service_token = client.get(
        "/v1/families/family_1/profiles",
        headers={"Authorization": f"Bearer {CORE_TOKEN}"},
    )
    assert service_token.status_code == 401

    listed = client.get("/v1/families/family_1/profiles", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["person_id"] == "person_erlan"
    assert listed.json()[0]["birth_date"]["value"] == "1978"

    fetched = client.get("/v1/families/family_1/profiles/person_erlan", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["canonical_name"] == "Ерлан"

    hidden = client.get("/v1/families/family_2/profiles/person_erlan", headers=headers)
    assert hidden.status_code == 404
    assert "person_erlan" not in hidden.text
