from __future__ import annotations

import os
import threading
from typing import Any

import pytest

from mura.identity.auth import VerifiedIdentity
from mura.identity.policy import Capability, FamilyRole, capabilities_for, role_allows
from mura.storage.database import Database
from mura.storage.identity import (
    FamilyMembershipRow,
    FamilyRow,
    IdentityRepository,
    MembershipNotFoundError,
    SoleOwnerError,
    UserRow,
    new_family_id,
    new_user_id,
)

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

ALICE = VerifiedIdentity(
    issuer="https://issuer.test/", subject="alice", email="a@b.test", display_name="Alice"
)
BOB = VerifiedIdentity(issuer="https://issuer.test/", subject="bob", display_name="Bob")


@pytest.fixture
def repository() -> IdentityRepository:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    return IdentityRepository(database)


# ------------------------------------------------------------------- policy


def test_role_capability_matrix() -> None:
    viewer = capabilities_for(FamilyRole.VIEWER)
    editor = capabilities_for(FamilyRole.EDITOR)
    owner = capabilities_for(FamilyRole.OWNER)

    # Viewer reads but never mutates.
    assert Capability.READ_RECORDINGS in viewer
    assert Capability.CREATE_RECORDING not in viewer
    assert Capability.RESOLVE_CONFLICTS not in viewer
    assert Capability.MANAGE_MEMBERS not in viewer

    # Editor adds archive mutation but never governance.
    assert viewer < editor
    assert Capability.CREATE_RECORDING in editor
    assert Capability.RESOLVE_CONFLICTS in editor
    assert Capability.MANAGE_MEMBERS not in editor
    assert Capability.UPDATE_FAMILY not in editor

    # Owner adds governance.
    assert editor < owner
    assert Capability.MANAGE_MEMBERS in owner
    assert Capability.UPDATE_FAMILY in owner


def test_role_allows_is_the_single_decision_point() -> None:
    assert role_allows(FamilyRole.EDITOR, Capability.CREATE_RECORDING)
    assert not role_allows(FamilyRole.VIEWER, Capability.CREATE_RECORDING)
    assert not role_allows(FamilyRole.EDITOR, Capability.MANAGE_MEMBERS)


# ---------------------------------------------------------------- identifiers


def test_identifiers_are_server_generated_and_namespaced() -> None:
    assert new_user_id().startswith("user_") and len(new_user_id()) == 37
    assert new_family_id().startswith("family_") and len(new_family_id()) == 39
    assert new_user_id() != new_user_id()


def test_user_id_is_never_the_provider_subject(repository: IdentityRepository) -> None:
    principal = repository.resolve_principal(ALICE)

    assert principal.user_id != ALICE.subject
    assert ALICE.subject not in principal.user_id


# ------------------------------------------------------------- provisioning


def test_first_login_creates_a_user_and_repeat_reuses_it(
    repository: IdentityRepository,
) -> None:
    first = repository.resolve_principal(ALICE)
    second = repository.resolve_principal(ALICE)

    assert first.user_id == second.user_id


def test_same_email_at_a_different_issuer_is_a_different_account(
    repository: IdentityRepository,
) -> None:
    one = repository.resolve_principal(ALICE)
    other_issuer = VerifiedIdentity(
        issuer="https://other-provider.test/", subject="alice", email=ALICE.email
    )

    two = repository.resolve_principal(other_issuer)

    # Email is not identity: these must never silently merge.
    assert one.user_id != two.user_id


def test_same_email_different_subject_is_a_different_account(
    repository: IdentityRepository,
) -> None:
    one = repository.resolve_principal(ALICE)
    twin = VerifiedIdentity(issuer=ALICE.issuer, subject="alice-2", email=ALICE.email)

    assert repository.resolve_principal(twin).user_id != one.user_id


def test_profile_metadata_refreshes_without_touching_privileged_state(
    repository: IdentityRepository,
) -> None:
    principal = repository.resolve_principal(ALICE)
    family = repository.create_family(name="Family", owner_user_id=principal.user_id)

    repository.resolve_principal(
        VerifiedIdentity(issuer=ALICE.issuer, subject=ALICE.subject, display_name="Renamed")
    )

    user = repository.get_user(principal.user_id)
    assert user is not None and user.display_name == "Renamed"
    # A token claim cannot grant or alter membership.
    membership = repository.get_membership(family_id=family.family_id, user_id=principal.user_id)
    assert membership is not None and membership.role == FamilyRole.OWNER.value


# ------------------------------------------------------------------ families


def test_creating_a_family_creates_the_owner_membership_atomically(
    repository: IdentityRepository,
) -> None:
    principal = repository.resolve_principal(ALICE)

    family = repository.create_family(name="Күләш", owner_user_id=principal.user_id)

    membership = repository.get_membership(family_id=family.family_id, user_id=principal.user_id)
    assert membership is not None
    assert membership.role == FamilyRole.OWNER.value
    assert family.created_by_user_id == principal.user_id


def test_listing_returns_only_families_the_user_belongs_to(
    repository: IdentityRepository,
) -> None:
    alice = repository.resolve_principal(ALICE)
    bob = repository.resolve_principal(BOB)
    mine = repository.create_family(name="Mine", owner_user_id=alice.user_id)
    repository.create_family(name="Theirs", owner_user_id=bob.user_id)

    listed = repository.list_families_for_user(alice.user_id)

    assert [family.family_id for family, _ in listed] == [mine.family_id]


def test_legacy_family_without_membership_is_invisible(
    repository: IdentityRepository,
) -> None:
    alice = repository.resolve_principal(ALICE)
    with repository.database.session_factory.begin() as session:
        session.add(FamilyRow(family_id="family_legacy", name="Legacy", created_by_user_id=None))

    assert repository.list_families_for_user(alice.user_id) == []
    assert (
        repository.get_family_for_member(family_id="family_legacy", user_id=alice.user_id) is None
    )


def test_non_member_cannot_read_a_family(repository: IdentityRepository) -> None:
    alice = repository.resolve_principal(ALICE)
    bob = repository.resolve_principal(BOB)
    family = repository.create_family(name="Private", owner_user_id=alice.user_id)

    assert repository.get_family_for_member(family_id=family.family_id, user_id=bob.user_id) is None


# --------------------------------------------------------------- memberships


def _family_with_two(repository: IdentityRepository) -> tuple[Any, str, str]:
    alice = repository.resolve_principal(ALICE)
    bob = repository.resolve_principal(BOB)
    family = repository.create_family(name="Shared", owner_user_id=alice.user_id)
    with repository.database.session_factory.begin() as session:
        session.add(
            FamilyMembershipRow(
                membership_id="membership_bob",
                family_id=family.family_id,
                user_id=bob.user_id,
                role=FamilyRole.VIEWER.value,
            )
        )
    return family, alice.user_id, bob.user_id


def test_members_are_listed_with_minimal_fields(repository: IdentityRepository) -> None:
    family, _, _ = _family_with_two(repository)

    members = repository.list_members(family.family_id)

    assert len(members) == 2
    for membership, user in members:
        assert isinstance(user, UserRow)
        assert membership.family_id == family.family_id


def test_role_can_be_changed_when_another_owner_remains(
    repository: IdentityRepository,
) -> None:
    family, alice_id, bob_id = _family_with_two(repository)
    repository.change_member_role(family_id=family.family_id, user_id=bob_id, role=FamilyRole.OWNER)

    repository.change_member_role(
        family_id=family.family_id, user_id=alice_id, role=FamilyRole.EDITOR
    )

    assert repository.count_owners(family.family_id) == 1


def test_unknown_membership_raises(repository: IdentityRepository) -> None:
    family, _, _ = _family_with_two(repository)

    with pytest.raises(MembershipNotFoundError):
        repository.change_member_role(
            family_id=family.family_id, user_id="user_missing", role=FamilyRole.VIEWER
        )


# ------------------------------------------------------------ owner invariant


def test_sole_owner_cannot_be_demoted(repository: IdentityRepository) -> None:
    family, alice_id, _ = _family_with_two(repository)

    with pytest.raises(SoleOwnerError):
        repository.change_member_role(
            family_id=family.family_id, user_id=alice_id, role=FamilyRole.VIEWER
        )

    assert repository.count_owners(family.family_id) == 1


def test_sole_owner_cannot_be_removed(repository: IdentityRepository) -> None:
    family, alice_id, _ = _family_with_two(repository)

    with pytest.raises(SoleOwnerError):
        repository.remove_member(family_id=family.family_id, user_id=alice_id)

    assert repository.count_owners(family.family_id) == 1


def test_owner_may_be_removed_once_a_second_owner_exists(
    repository: IdentityRepository,
) -> None:
    family, alice_id, bob_id = _family_with_two(repository)
    repository.change_member_role(family_id=family.family_id, user_id=bob_id, role=FamilyRole.OWNER)

    repository.remove_member(family_id=family.family_id, user_id=alice_id)

    assert repository.count_owners(family.family_id) == 1


def test_non_owner_removal_is_always_allowed(repository: IdentityRepository) -> None:
    family, _, bob_id = _family_with_two(repository)

    repository.remove_member(family_id=family.family_id, user_id=bob_id)

    assert len(repository.list_members(family.family_id)) == 1


# ------------------------------------------------------- real PostgreSQL only


pg_only = pytest.mark.skipif(
    not POSTGRES_URL or "test" not in (POSTGRES_URL or "").rsplit("/", 1)[-1].lower(),
    reason="TEST_POSTGRES_URL pointing at a disposable test database is required",
)


@pytest.fixture
def pg_repository() -> IdentityRepository:
    assert POSTGRES_URL is not None
    database = Database(POSTGRES_URL)
    database.create_schema()
    repo = IdentityRepository(database)
    with database.session_factory.begin() as session:
        session.query(FamilyMembershipRow).delete()
        session.query(FamilyRow).filter(FamilyRow.created_by_user_id.is_not(None)).delete()
        session.query(UserRow).delete()
    return repo


@pg_only
def test_postgres_concurrent_first_login_creates_one_user(
    pg_repository: IdentityRepository,
) -> None:
    barrier = threading.Barrier(4)
    results: list[str] = []
    errors: list[BaseException] = []

    def login() -> None:
        try:
            barrier.wait(timeout=10)
            results.append(pg_repository.resolve_principal(ALICE).user_id)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=login) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    # Four simultaneous first logins, exactly one account.
    assert len(set(results)) == 1


@pg_only
def test_postgres_membership_uniqueness_is_enforced(
    pg_repository: IdentityRepository,
) -> None:
    from sqlalchemy.exc import IntegrityError

    alice = pg_repository.resolve_principal(ALICE)
    family = pg_repository.create_family(name="Unique", owner_user_id=alice.user_id)

    with pytest.raises(IntegrityError):
        with pg_repository.database.session_factory.begin() as session:
            session.add(
                FamilyMembershipRow(
                    membership_id="membership_dupe",
                    family_id=family.family_id,
                    user_id=alice.user_id,
                    role=FamilyRole.VIEWER.value,
                )
            )


@pg_only
def test_postgres_concurrent_owner_demotion_cannot_reach_zero_owners(
    pg_repository: IdentityRepository,
) -> None:
    alice = pg_repository.resolve_principal(ALICE)
    bob = pg_repository.resolve_principal(BOB)
    family = pg_repository.create_family(name="Race", owner_user_id=alice.user_id)
    with pg_repository.database.session_factory.begin() as session:
        session.add(
            FamilyMembershipRow(
                membership_id="membership_bob_pg",
                family_id=family.family_id,
                user_id=bob.user_id,
                role=FamilyRole.OWNER.value,
            )
        )

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def demote(user_id: str) -> None:
        barrier.wait(timeout=10)
        try:
            pg_repository.change_member_role(
                family_id=family.family_id, user_id=user_id, role=FamilyRole.VIEWER
            )
            outcomes.append("demoted")
        except SoleOwnerError:
            outcomes.append("refused")

    threads = [
        threading.Thread(target=demote, args=(alice.user_id,)),
        threading.Thread(target=demote, args=(bob.user_id,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    # Both owners demoting at once must not leave the family ownerless.
    assert pg_repository.count_owners(family.family_id) >= 1
    assert outcomes.count("refused") >= 1


@pg_only
def test_postgres_family_listing_is_membership_isolated(
    pg_repository: IdentityRepository,
) -> None:
    alice = pg_repository.resolve_principal(ALICE)
    bob = pg_repository.resolve_principal(BOB)
    mine = pg_repository.create_family(name="Mine", owner_user_id=alice.user_id)
    pg_repository.create_family(name="Theirs", owner_user_id=bob.user_id)

    listed = pg_repository.list_families_for_user(alice.user_id)

    assert [family.family_id for family, _ in listed] == [mine.family_id]
