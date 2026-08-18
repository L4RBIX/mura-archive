from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api.authz import (
    build_capability_dependency,
    build_family_context_dependency,
    family_not_found,
    insufficient_family_role,
)
from apps.api.main import (
    create_app,
    get_auth_verifier,
    get_runtime,
    get_settings,
)
from mura.config import CoreSettings
from mura.identity.context import (
    AuthorizedFamilyContext,
    FamilyAccessDenied,
    FamilyAuthorizationService,
    InsufficientFamilyRole,
)
from mura.identity.policy import Capability, FamilyRole
from mura.storage.database import Database
from mura.storage.identity import FamilyMembershipRow, FamilyRow, IdentityRepository, UserRow
from tests.authz_factories import (
    FakePrincipalVerifier,
    TestIdentity,
    create_membership,
    create_test_family,
    create_test_user,
    seed_conflict_for_family,
    seed_profile_for_family,
    seed_recording_for_family,
)

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
CORE_TOKEN = "c" * 40
OPERATIONS_TOKEN = "o" * 40
WORKER_TOKEN = "r" * 40


def _settings(**overrides: Any) -> CoreSettings:
    payload: dict[str, Any] = {
        "DEEPSEEK_API_KEY": "sk-" + "d" * 40,
        "CORE_API_KEY": CORE_TOKEN,
        "OPERATIONS_API_KEY": OPERATIONS_TOKEN,
        "WORKER_REGISTRATION_TOKEN": WORKER_TOKEN,
        "KAGGLE_ASR_API_KEY": "a" * 40,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "DATABASE_AUTO_CREATE": True,
    }
    payload.update(overrides)
    return CoreSettings.model_validate(payload)


class _Runtime:
    def __init__(self, database: Database) -> None:
        self.database = database


@pytest.fixture
def world(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Two families, four identities, and resources on both sides."""

    settings = _settings()
    database = Database(settings.database_url)
    database.create_schema()
    identity = IdentityRepository(database)
    verifier = FakePrincipalVerifier()

    owner_a = create_test_user(identity, subject="owner-a", verifier=verifier)
    editor_a = create_test_user(identity, subject="editor-a", verifier=verifier)
    viewer_a = create_test_user(identity, subject="viewer-a", verifier=verifier)
    outsider = create_test_user(identity, subject="outsider", verifier=verifier)
    owner_b = create_test_user(identity, subject="owner-b", verifier=verifier)

    family_a = create_test_family(identity, name="Family A", owner=owner_a)
    family_b = create_test_family(identity, name="Family B", owner=owner_b)
    create_membership(database, family_id=family_a, user=editor_a, role=FamilyRole.EDITOR)
    create_membership(database, family_id=family_a, user=viewer_a, role=FamilyRole.VIEWER)

    seed_recording_for_family(
        database, family_id=family_a, recording_id="rec_" + "a" * 32, job_id="job_" + "a" * 32
    )
    seed_recording_for_family(
        database, family_id=family_b, recording_id="rec_" + "b" * 32, job_id="job_" + "b" * 32
    )
    seed_profile_for_family(database, family_id=family_b, person_id="person_" + "b" * 32)
    seed_conflict_for_family(database, family_id=family_b, conflict_id="conflict_" + "b" * 32)

    application = create_app(settings)
    runtime = _Runtime(database)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_runtime] = lambda: runtime
    application.dependency_overrides[get_auth_verifier] = lambda: verifier

    yield {
        "client": TestClient(application, raise_server_exceptions=False),
        "database": database,
        "identity": identity,
        "service": FamilyAuthorizationService(database),
        "owner_a": owner_a,
        "editor_a": editor_a,
        "viewer_a": viewer_a,
        "outsider": outsider,
        "owner_b": owner_b,
        "family_a": family_a,
        "family_b": family_b,
    }


# ------------------------------------------------------- authorized context


def test_member_resolves_to_a_context_with_their_role(world: dict[str, Any]) -> None:
    context = world["service"].authorize(world["editor_a"].principal, world["family_a"])

    assert isinstance(context, AuthorizedFamilyContext)
    assert context.role is FamilyRole.EDITOR
    assert context.family_id == world["family_a"]
    assert context.user_id == world["editor_a"].user_id


def test_non_member_is_denied(world: dict[str, Any]) -> None:
    with pytest.raises(FamilyAccessDenied):
        world["service"].authorize(world["outsider"].principal, world["family_a"])


def test_absent_family_is_denied_identically(world: dict[str, Any]) -> None:
    with pytest.raises(FamilyAccessDenied):
        world["service"].authorize(world["owner_a"].principal, "family_does_not_exist")


def test_member_of_another_family_cannot_cross_over(world: dict[str, Any]) -> None:
    with pytest.raises(FamilyAccessDenied):
        world["service"].authorize(world["owner_b"].principal, world["family_a"])


# ------------------------------------------------------------- capabilities


@pytest.mark.parametrize(
    ("role", "capability", "allowed"),
    [
        (FamilyRole.VIEWER, Capability.READ_RECORDINGS, True),
        (FamilyRole.VIEWER, Capability.READ_CONFLICTS, True),
        (FamilyRole.VIEWER, Capability.CREATE_RECORDING, False),
        (FamilyRole.VIEWER, Capability.RESOLVE_CONFLICTS, False),
        (FamilyRole.VIEWER, Capability.MANAGE_MEMBERS, False),
        (FamilyRole.EDITOR, Capability.READ_RECORDINGS, True),
        (FamilyRole.EDITOR, Capability.CREATE_RECORDING, True),
        (FamilyRole.EDITOR, Capability.RESOLVE_CONFLICTS, True),
        (FamilyRole.EDITOR, Capability.MANAGE_MEMBERS, False),
        (FamilyRole.OWNER, Capability.CREATE_RECORDING, True),
        (FamilyRole.OWNER, Capability.RESOLVE_CONFLICTS, True),
        (FamilyRole.OWNER, Capability.MANAGE_MEMBERS, True),
    ],
)
def test_capability_matrix_through_the_context(
    world: dict[str, Any], role: FamilyRole, capability: Capability, allowed: bool
) -> None:
    user = {
        FamilyRole.OWNER: world["owner_a"],
        FamilyRole.EDITOR: world["editor_a"],
        FamilyRole.VIEWER: world["viewer_a"],
    }[role]
    context = world["service"].authorize(user.principal, world["family_a"])

    assert context.allows(capability) is allowed
    if allowed:
        context.require(capability)
    else:
        with pytest.raises(InsufficientFamilyRole):
            context.require(capability)


def test_error_helpers_carry_the_canonical_status_codes() -> None:
    assert family_not_found().status_code == 404
    assert insufficient_family_role().status_code == 403


def test_dependency_builders_are_reusable() -> None:
    context_dependency = build_family_context_dependency(
        principal_dependency=lambda: None, authorization_service_dependency=lambda: None
    )
    guard = build_capability_dependency(
        Capability.CREATE_RECORDING, family_context_dependency=context_dependency
    )

    assert callable(context_dependency)
    assert callable(guard)


# ----------------------------------------------------- membership admin HTTP


def _patch(world: dict[str, Any], actor: TestIdentity, target: TestIdentity, role: str):
    return world["client"].patch(
        f"/v1/families/{world['family_a']}/members/{target.user_id}",
        headers=actor.headers,
        json={"role": role},
    )


def _delete(world: dict[str, Any], actor: TestIdentity, target: TestIdentity):
    return world["client"].delete(
        f"/v1/families/{world['family_a']}/members/{target.user_id}",
        headers=actor.headers,
    )


def test_owner_may_change_a_member_role(world: dict[str, Any]) -> None:
    response = _patch(world, world["owner_a"], world["viewer_a"], "editor")

    assert response.status_code == 200
    assert response.json()["role"] == "editor"


def test_owner_may_remove_a_member(world: dict[str, Any]) -> None:
    assert _delete(world, world["owner_a"], world["viewer_a"]).status_code == 204


@pytest.mark.parametrize("actor_key", ["editor_a", "viewer_a"])
def test_non_owners_cannot_administer_membership(world: dict[str, Any], actor_key: str) -> None:
    response = _patch(world, world[actor_key], world["viewer_a"], "owner")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_family_role"


def test_outsider_cannot_even_see_the_membership_route(world: dict[str, Any]) -> None:
    response = _patch(world, world["outsider"], world["viewer_a"], "viewer")

    # 404, not 403: never confirm that family_A exists.
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "family_not_found"
    # The response must not disclose the family, the target user, or the reason.
    assert world["family_a"] not in response.text
    assert world["viewer_a"].user_id not in response.text


def test_unauthenticated_membership_mutation_is_rejected(world: dict[str, Any]) -> None:
    response = world["client"].patch(
        f"/v1/families/{world['family_a']}/members/{world['viewer_a'].user_id}",
        json={"role": "viewer"},
    )

    assert response.status_code == 401


def test_core_api_key_cannot_administer_membership(world: dict[str, Any]) -> None:
    response = world["client"].patch(
        f"/v1/families/{world['family_a']}/members/{world['viewer_a'].user_id}",
        headers={"Authorization": f"Bearer {CORE_TOKEN}"},
        json={"role": "owner"},
    )

    # The service token is not a user identity on Principal-native routes.
    assert response.status_code == 401


def test_member_of_another_family_is_not_found_as_a_target(world: dict[str, Any]) -> None:
    response = _patch(world, world["owner_a"], world["owner_b"], "viewer")

    # A user id from another family must not reveal that the account exists.
    assert response.status_code == 404


# ------------------------------------------------------- sole owner via HTTP


def test_sole_owner_cannot_be_demoted_through_http(world: dict[str, Any]) -> None:
    response = _patch(world, world["owner_a"], world["owner_a"], "editor")

    assert response.status_code == 409
    assert world["identity"].count_owners(world["family_a"]) == 1


def test_sole_owner_cannot_be_removed_through_http(world: dict[str, Any]) -> None:
    response = _delete(world, world["owner_a"], world["owner_a"])

    assert response.status_code == 409
    assert world["identity"].count_owners(world["family_a"]) == 1


def test_owner_may_step_down_once_a_second_owner_exists(world: dict[str, Any]) -> None:
    assert _patch(world, world["owner_a"], world["editor_a"], "owner").status_code == 200

    assert _patch(world, world["owner_a"], world["owner_a"], "viewer").status_code == 200
    assert world["identity"].count_owners(world["family_a"]) == 1


def test_owner_may_be_removed_once_a_second_owner_exists(world: dict[str, Any]) -> None:
    _patch(world, world["owner_a"], world["editor_a"], "owner")

    assert _delete(world, world["owner_a"], world["owner_a"]).status_code == 204
    assert world["identity"].count_owners(world["family_a"]) == 1


# --------------------------------------------------------- first-login rules


def test_first_login_grants_no_family_access(world: dict[str, Any]) -> None:
    newcomer = create_test_user(
        world["identity"],
        subject="brand-new",
        verifier=world["client"].app.dependency_overrides[get_auth_verifier](),
    )

    response = world["client"].get("/v1/families", headers=newcomer.headers)

    assert response.status_code == 200
    assert response.json() == []


def test_principal_user_id_is_never_an_archive_person_id(world: dict[str, Any]) -> None:
    user_id = world["owner_a"].user_id

    # An account id is not a family-tree person and must never be usable as one.
    assert user_id.startswith("user_")
    assert not user_id.startswith("person_")
    with world["database"].session_factory() as session:
        assert session.get(UserRow, user_id) is not None
        from mura.storage.archive import ArchivePersonRow

        assert session.get(ArchivePersonRow, user_id) is None


# ---------------------------------------------------- BOLA harness (service)


@pytest.mark.parametrize("actor_key", ["owner_a", "editor_a", "viewer_a"])
def test_no_role_in_family_a_can_authorize_into_family_b(
    world: dict[str, Any], actor_key: str
) -> None:
    with pytest.raises(FamilyAccessDenied):
        world["service"].authorize(world[actor_key].principal, world["family_b"])


def test_family_b_resources_exist_but_are_unreachable_from_family_a(
    world: dict[str, Any],
) -> None:
    # The harness proves the foreign resources are real, so a later 404 is
    # authorization rather than an accidentally empty database.
    with world["database"].session_factory() as session:
        assert session.get(FamilyRow, world["family_b"]) is not None
    with pytest.raises(FamilyAccessDenied):
        world["service"].authorize(world["viewer_a"].principal, world["family_b"])


# ------------------------------------------------------- real PostgreSQL


pg_only = pytest.mark.skipif(
    not POSTGRES_URL or "test" not in (POSTGRES_URL or "").rsplit("/", 1)[-1].lower(),
    reason="TEST_POSTGRES_URL pointing at a disposable test database is required",
)


@pytest.fixture
def pg_identity() -> IdentityRepository:
    assert POSTGRES_URL is not None
    database = Database(POSTGRES_URL)
    database.create_schema()
    with database.session_factory.begin() as session:
        session.query(FamilyMembershipRow).delete()
        session.query(FamilyRow).filter(FamilyRow.created_by_user_id.is_not(None)).delete()
        session.query(UserRow).delete()
    return IdentityRepository(database)


@pg_only
def test_postgres_authorization_lookup_is_membership_scoped(
    pg_identity: IdentityRepository,
) -> None:
    service = FamilyAuthorizationService(pg_identity.database)
    owner = create_test_user(pg_identity, subject="pg-owner")
    outsider = create_test_user(pg_identity, subject="pg-outsider")
    family_id = create_test_family(pg_identity, name="PG", owner=owner)

    assert service.authorize(owner.principal, family_id).role is FamilyRole.OWNER
    with pytest.raises(FamilyAccessDenied):
        service.authorize(outsider.principal, family_id)


@pg_only
def test_postgres_concurrent_owner_mutation_never_reaches_zero(
    pg_identity: IdentityRepository,
) -> None:
    first = create_test_user(pg_identity, subject="pg-owner-1")
    second = create_test_user(pg_identity, subject="pg-owner-2")
    family_id = create_test_family(pg_identity, name="PG Race", owner=first)
    create_membership(pg_identity.database, family_id=family_id, user=second, role=FamilyRole.OWNER)

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def demote(user_id: str) -> None:
        from mura.storage.identity import SoleOwnerError

        barrier.wait(timeout=10)
        try:
            pg_identity.change_member_role(
                family_id=family_id, user_id=user_id, role=FamilyRole.VIEWER
            )
            outcomes.append("demoted")
        except SoleOwnerError:
            outcomes.append("refused")

    threads = [
        threading.Thread(target=demote, args=(first.user_id,)),
        threading.Thread(target=demote, args=(second.user_id,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert pg_identity.count_owners(family_id) >= 1
    assert outcomes.count("refused") >= 1


@pg_only
def test_postgres_first_login_reuses_the_same_internal_user(
    pg_identity: IdentityRepository,
) -> None:
    first = create_test_user(pg_identity, subject="pg-repeat")
    second = create_test_user(pg_identity, subject="pg-repeat")

    assert first.user_id == second.user_id


@pg_only
def test_postgres_membership_list_is_isolated(pg_identity: IdentityRepository) -> None:
    owner_one = create_test_user(pg_identity, subject="pg-iso-1")
    owner_two = create_test_user(pg_identity, subject="pg-iso-2")
    mine = create_test_family(pg_identity, name="Mine", owner=owner_one)
    create_test_family(pg_identity, name="Theirs", owner=owner_two)

    listed = pg_identity.list_families_for_user(owner_one.user_id)

    assert [family.family_id for family, _ in listed] == [mine]
