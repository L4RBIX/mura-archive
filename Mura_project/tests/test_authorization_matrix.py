"""The authorization model, exercised through real HTTP routes.

PR-03B-PREP proved the policy in isolation. This suite proves the deployed
surface: every assertion goes through the actual FastAPI app, with real user
rows, real membership rows and real family-scoped archive data, because a
capability table that is correct in isolation protects nothing if a route
forgot to consult it.

Three matrices run here. The role matrix asks what each family role may do. The
BOLA matrix asks whether a legitimate member can reach another family's resource
by substituting an id. The credential matrix asks whether each of the four
credentials stays inside its own class of routes.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import (
    create_app,
    get_auth_verifier,
    get_family_authorization_service,
    get_runtime,
    get_settings,
    require_read_conflicts,
    require_read_recordings,
)
from mura.config import CoreSettings
from mura.identity.context import FamilyAuthorizationService
from mura.identity.policy import FamilyRole
from mura.orchestration import LocalAudioStorage
from mura.storage.archive import ArchiveConflictRow
from mura.storage.database import (
    Database,
    PipelineResultRow,
    ProcessingJobRow,
    RecordingRepository,
    RecordingRow,
)
from mura.storage.identity import (
    FamilyMembershipRow,
    FamilyRow,
    IdentityRepository,
    UserRow,
)
from mura.storage.profile_models import MaterializedPersonProfileRow
from tests.authz_factories import (
    ISSUER,
    WAV_BYTES,
    FakePrincipalVerifier,
    TestIdentity,
    create_family_with_id,
    create_membership,
    create_test_user,
    seed_conflict_for_family,
    seed_materialized_profile_for_family,
    seed_recording_for_family,
)

CORE_TOKEN = "c" * 40
OPERATIONS_TOKEN = "o" * 40
WORKER_TOKEN = "r" * 40

FAMILY_A = "family_authz_a"
FAMILY_B = "family_authz_b"
REC_A, REC_B = "rec_" + "a" * 32, "rec_" + "b" * 32
JOB_A, JOB_B = "job_" + "a" * 32, "job_" + "b" * 32
PERSON_A, PERSON_B = "person_" + "a" * 32, "person_" + "b" * 32
CONFLICT_A, CONFLICT_B = "conflict_" + "a" * 32, "conflict_" + "b" * 32
STORY_A, STORY_B = "story_" + "a" * 32, "story_" + "b" * 32

#: Ids that belong to family B. No family A caller may ever surface one.
FOREIGN_IDS = (FAMILY_B, REC_B, JOB_B, PERSON_B, CONFLICT_B)


def _settings() -> CoreSettings:
    return CoreSettings.model_validate(
        {
            "DEEPSEEK_API_KEY": "sk-" + "d" * 40,
            "CORE_API_KEY": CORE_TOKEN,
            "OPERATIONS_API_KEY": OPERATIONS_TOKEN,
            "WORKER_REGISTRATION_TOKEN": WORKER_TOKEN,
            "KAGGLE_ASR_API_KEY": "a" * 40,
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "DATABASE_AUTO_CREATE": True,
        }
    )


class _Runtime:
    def __init__(self, database: Database, tmp_path: Path) -> None:
        self.database = database
        self.repository = RecordingRepository(database)
        self.storage = LocalAudioStorage(tmp_path / "audio", max_upload_bytes=1024 * 1024)


class World:
    """Two families with a full role set each, and archive data on both sides."""

    def __init__(self, tmp_path: Path, database: Database | None = None) -> None:
        self.settings = _settings()
        self.database = database if database is not None else Database(self.settings.database_url)
        self.database.create_schema()
        self.identity = IdentityRepository(self.database)
        self.verifier = FakePrincipalVerifier()

        self.owner_a = self._user("owner-a")
        self.editor_a = self._user("editor-a")
        self.viewer_a = self._user("viewer-a")
        self.second_owner_a = self._user("second-owner-a")
        self.outsider = self._user("outsider")
        self.owner_b = self._user("owner-b")

        create_family_with_id(self.database, family_id=FAMILY_A, name="A", owner=self.owner_a)
        create_family_with_id(self.database, family_id=FAMILY_B, name="B", owner=self.owner_b)
        for user, role in (
            (self.editor_a, FamilyRole.EDITOR),
            (self.viewer_a, FamilyRole.VIEWER),
            (self.second_owner_a, FamilyRole.OWNER),
        ):
            create_membership(self.database, family_id=FAMILY_A, user=user, role=role)

        for family, recording, job, person, conflict in (
            (FAMILY_A, REC_A, JOB_A, PERSON_A, CONFLICT_A),
            (FAMILY_B, REC_B, JOB_B, PERSON_B, CONFLICT_B),
        ):
            seed_recording_for_family(
                self.database, family_id=family, recording_id=recording, job_id=job
            )
            seed_materialized_profile_for_family(self.database, family_id=family, person_id=person)
            seed_conflict_for_family(self.database, family_id=family, conflict_id=conflict)

        self.app = create_app(self.settings)
        runtime = _Runtime(self.database, tmp_path)
        self.app.dependency_overrides[get_settings] = lambda: self.settings
        self.app.dependency_overrides[get_runtime] = lambda: runtime
        self.app.dependency_overrides[get_auth_verifier] = lambda: self.verifier
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def _user(self, subject: str) -> TestIdentity:
        return create_test_user(self.identity, subject=subject, verifier=self.verifier)


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    yield World(tmp_path)


def _token(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def _upload_kwargs() -> dict[str, Any]:
    return {
        "files": {"file": ("memory.wav", WAV_BYTES, "audio/wav")},
        "data": {"speaker_name": "Айсұлу"},
    }


# --------------------------------------------------------------- role matrix

#: (label, method, path template, body) for every family-scoped user route.
READ_ROUTES = [
    ("family", "get", f"/v1/families/{FAMILY_A}"),
    ("members", "get", f"/v1/families/{FAMILY_A}/members"),
    ("recording", "get", f"/v1/families/{FAMILY_A}/recordings/{REC_A}"),
    ("review-items", "get", f"/v1/families/{FAMILY_A}/recordings/{REC_A}/review-items"),
    ("job", "get", f"/v1/families/{FAMILY_A}/jobs/{JOB_A}"),
    ("profiles", "get", f"/v1/families/{FAMILY_A}/profiles"),
    ("profile", "get", f"/v1/families/{FAMILY_A}/profiles/{PERSON_A}"),
    ("conflicts", "get", f"/v1/families/{FAMILY_A}/conflicts"),
    ("conflict", "get", f"/v1/families/{FAMILY_A}/conflicts/{CONFLICT_A}"),
    # PR-06 archive read models. Added here rather than trusting the
    # classification test, which proves a route declares a credential and not
    # that the route enforces one.
    ("archive", "get", f"/v1/families/{FAMILY_A}/archive"),
    ("people", "get", f"/v1/families/{FAMILY_A}/people"),
    ("relationships", "get", f"/v1/families/{FAMILY_A}/relationships"),
    ("stories", "get", f"/v1/families/{FAMILY_A}/stories"),
    ("family-review", "get", f"/v1/families/{FAMILY_A}/review-items"),
]

DECISION_BODY = {"reviewer_reference": "reviewer:matrix", "note": "matrix authorization probe"}
MUTATION_ROUTES = [
    (
        "resolve",
        f"/v1/families/{FAMILY_A}/conflicts/{CONFLICT_A}/resolve",
        {**DECISION_BODY, "preferred_claim_id": "claim_x"},
    ),
    ("dismiss", f"/v1/families/{FAMILY_A}/conflicts/{CONFLICT_A}/dismiss", DECISION_BODY),
    ("reopen", f"/v1/families/{FAMILY_A}/conflicts/{CONFLICT_A}/reopen", DECISION_BODY),
]


@pytest.mark.parametrize("role", ["viewer", "editor", "owner"])
@pytest.mark.parametrize(("label", "method", "path"), READ_ROUTES)
def test_every_role_may_read_family_data(
    world: World, role: str, label: str, method: str, path: str
) -> None:
    del label
    actor = {"viewer": world.viewer_a, "editor": world.editor_a, "owner": world.owner_a}[role]

    response = getattr(world.client, method)(path, headers=actor.headers)

    assert response.status_code == 200


@pytest.mark.parametrize(("label", "path", "body"), MUTATION_ROUTES)
def test_a_viewer_may_not_mutate_the_archive(
    world: World, label: str, path: str, body: dict[str, Any]
) -> None:
    del label
    response = world.client.post(path, headers=world.viewer_a.headers, json=body)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_family_role"


def test_a_viewer_may_not_create_a_recording(world: World) -> None:
    response = world.client.post(
        f"/v1/families/{FAMILY_A}/recordings",
        headers=world.viewer_a.headers,
        **_upload_kwargs(),
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["editor", "owner"])
@pytest.mark.parametrize(("label", "path", "body"), MUTATION_ROUTES)
def test_editors_and_owners_pass_archive_authorization(
    world: World, role: str, label: str, path: str, body: dict[str, Any]
) -> None:
    """Authorization is the subject here, so the assertion is 'not refused'.

    A conflict transition can still fail on its own merits -- wrong claim id, or
    an already-open conflict -- and that is a 409/422 about the archive, not a
    verdict about the caller. Conflating the two would let a genuine 403
    regression hide behind a state error.
    """

    del label
    actor = {"editor": world.editor_a, "owner": world.owner_a}[role]

    response = world.client.post(path, headers=actor.headers, json=body)

    assert response.status_code not in (401, 403, 404)


@pytest.mark.parametrize("role", ["editor", "owner"])
def test_editors_and_owners_may_create_a_recording(world: World, role: str) -> None:
    actor = {"editor": world.editor_a, "owner": world.owner_a}[role]

    response = world.client.post(
        f"/v1/families/{FAMILY_A}/recordings", headers=actor.headers, **_upload_kwargs()
    )

    assert response.status_code == 202


@pytest.mark.parametrize("role", ["viewer", "editor"])
def test_only_an_owner_administers_membership(world: World, role: str) -> None:
    actor = {"viewer": world.viewer_a, "editor": world.editor_a}[role]
    target = f"/v1/families/{FAMILY_A}/members/{world.viewer_a.user_id}"

    patched = world.client.patch(target, headers=actor.headers, json={"role": "editor"})
    deleted = world.client.delete(target, headers=actor.headers)

    assert patched.status_code == 403
    assert deleted.status_code == 403


def test_an_owner_may_administer_membership(world: World) -> None:
    target = f"/v1/families/{FAMILY_A}/members/{world.viewer_a.user_id}"

    patched = world.client.patch(target, headers=world.owner_a.headers, json={"role": "editor"})

    assert patched.status_code == 200
    assert patched.json()["role"] == "editor"
    assert world.client.delete(target, headers=world.owner_a.headers).status_code == 204


# ------------------------------------------------------- owner invariant, HTTP


def test_a_sole_owner_cannot_demote_or_remove_themselves(world: World) -> None:
    # Remove the second owner first, so owner_a is genuinely alone.
    target_second = f"/v1/families/{FAMILY_A}/members/{world.second_owner_a.user_id}"
    assert world.client.delete(target_second, headers=world.owner_a.headers).status_code == 204

    target_self = f"/v1/families/{FAMILY_A}/members/{world.owner_a.user_id}"
    demoted = world.client.patch(
        target_self, headers=world.owner_a.headers, json={"role": "viewer"}
    )
    removed = world.client.delete(target_self, headers=world.owner_a.headers)

    assert demoted.status_code == 409
    assert removed.status_code == 409
    assert demoted.json()["error"]["code"] == "sole_owner_required"
    assert world.identity.count_owners(FAMILY_A) == 1


def test_one_of_two_owners_may_be_demoted(world: World) -> None:
    target = f"/v1/families/{FAMILY_A}/members/{world.second_owner_a.user_id}"

    response = world.client.patch(target, headers=world.owner_a.headers, json={"role": "viewer"})

    assert response.status_code == 200
    assert world.identity.count_owners(FAMILY_A) == 1


# --------------------------------------------------------------- BOLA / IDOR

#: A family A member substitutes a family B resource id into a family A path.
CROSS_FAMILY_ROUTES = [
    ("recording", f"/v1/families/{FAMILY_A}/recordings/{REC_B}"),
    ("review-items", f"/v1/families/{FAMILY_A}/recordings/{REC_B}/review-items"),
    ("job", f"/v1/families/{FAMILY_A}/jobs/{JOB_B}"),
    ("profile", f"/v1/families/{FAMILY_A}/profiles/{PERSON_B}"),
    ("conflict", f"/v1/families/{FAMILY_A}/conflicts/{CONFLICT_B}"),
    # Another family's story or recording, addressed through a family the
    # caller does belong to: the id must not be a way to reach across.
    ("story", f"/v1/families/{FAMILY_A}/stories/{STORY_B}"),
    ("audio", f"/v1/families/{FAMILY_A}/recordings/{REC_B}/audio"),
]


@pytest.mark.parametrize("role", ["viewer", "editor", "owner"])
@pytest.mark.parametrize(("label", "path"), CROSS_FAMILY_ROUTES)
def test_membership_never_reaches_another_familys_resource(
    world: World, role: str, label: str, path: str
) -> None:
    """The second layer: authorization passes, resource integrity still refuses.

    The caller really is a member of the family in the path, including as its
    owner -- the strongest family role is still an outsider everywhere else.
    """

    del label
    actor = {"viewer": world.viewer_a, "editor": world.editor_a, "owner": world.owner_a}[role]

    response = world.client.get(path, headers=actor.headers)

    assert response.status_code == 404


@pytest.mark.parametrize(("label", "path", "body"), MUTATION_ROUTES)
def test_conflict_mutations_are_family_scoped(
    world: World, label: str, path: str, body: dict[str, Any]
) -> None:
    del label
    foreign = path.replace(CONFLICT_A, CONFLICT_B)

    response = world.client.post(foreign, headers=world.owner_a.headers, json=body)

    assert response.status_code == 404


#: An authenticated stranger addressing family A's own resources.
OUTSIDER_ROUTES = [
    ("family", f"/v1/families/{FAMILY_A}"),
    ("members", f"/v1/families/{FAMILY_A}/members"),
    ("recording", f"/v1/families/{FAMILY_A}/recordings/{REC_A}"),
    ("review-items", f"/v1/families/{FAMILY_A}/recordings/{REC_A}/review-items"),
    ("job", f"/v1/families/{FAMILY_A}/jobs/{JOB_A}"),
    ("profiles", f"/v1/families/{FAMILY_A}/profiles"),
    ("profile", f"/v1/families/{FAMILY_A}/profiles/{PERSON_A}"),
    ("conflicts", f"/v1/families/{FAMILY_A}/conflicts"),
    ("conflict", f"/v1/families/{FAMILY_A}/conflicts/{CONFLICT_A}"),
    ("archive", f"/v1/families/{FAMILY_A}/archive"),
    ("people", f"/v1/families/{FAMILY_A}/people"),
    ("relationships", f"/v1/families/{FAMILY_A}/relationships"),
    ("stories", f"/v1/families/{FAMILY_A}/stories"),
    ("story", f"/v1/families/{FAMILY_A}/stories/{STORY_A}"),
    ("family-review", f"/v1/families/{FAMILY_A}/review-items"),
    ("audio", f"/v1/families/{FAMILY_A}/recordings/{REC_A}/audio"),
]


@pytest.mark.parametrize(("label", "path"), OUTSIDER_ROUTES)
def test_a_non_member_is_not_told_the_family_exists(world: World, label: str, path: str) -> None:
    del label
    response = world.client.get(path, headers=world.outsider.headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "family_not_found"


@pytest.mark.parametrize(("label", "path"), OUTSIDER_ROUTES)
def test_a_non_member_gets_the_same_answer_for_a_family_that_does_not_exist(
    world: World, label: str, path: str
) -> None:
    """Absent and private must be indistinguishable, or 404 becomes an oracle."""

    del label
    real = world.client.get(path, headers=world.outsider.headers)
    invented = world.client.get(
        path.replace(FAMILY_A, "family_does_not_exist"), headers=world.outsider.headers
    )

    assert real.status_code == invented.status_code == 404
    assert real.json()["error"]["code"] == invented.json()["error"]["code"]
    assert real.json()["error"]["message"] == invented.json()["error"]["message"]


def test_an_owner_of_one_family_is_an_outsider_to_another(world: World) -> None:
    response = world.client.get(f"/v1/families/{FAMILY_B}", headers=world.owner_a.headers)

    assert response.status_code == 404


# ------------------------------------------------------------ non-disclosure


@pytest.mark.parametrize(("label", "path"), CROSS_FAMILY_ROUTES + OUTSIDER_ROUTES)
def test_refusals_never_echo_an_identifier(world: World, label: str, path: str) -> None:
    """Error bodies are table-driven, and this proves it stays that way."""

    del label
    for actor in (world.owner_a, world.outsider):
        body = world.client.get(path, headers=actor.headers).text
        if not body:
            continue
        for identifier in FOREIGN_IDS:
            assert identifier not in body


def test_membership_refusals_never_echo_the_target_user(world: World) -> None:
    target = f"/v1/families/{FAMILY_A}/members/{world.viewer_a.user_id}"

    response = world.client.patch(target, headers=world.editor_a.headers, json={"role": "owner"})

    assert response.status_code == 403
    assert world.viewer_a.user_id not in response.text
    assert FAMILY_A not in response.text


# ------------------------------------------------------- credential crossover

USER_APP_PROBE = ("get", f"/v1/families/{FAMILY_A}/recordings/{REC_A}")
SERVICE_PROBES = [
    ("get", f"/v1/jobs/{JOB_A}/trace"),
    ("get", f"/v1/families/{FAMILY_A}/replays"),
]
OPERATIONS_PROBE = ("get", "/v1/operations/release")
WORKER_PROBE = ("get", "/v1/workers/current")


@pytest.mark.parametrize("token", [CORE_TOKEN, OPERATIONS_TOKEN, WORKER_TOKEN])
def test_no_machine_credential_reads_family_data(world: World, token: str) -> None:
    method, path = USER_APP_PROBE

    response = getattr(world.client, method)(path, headers=_token(token))

    assert response.status_code == 401


@pytest.mark.parametrize("token", [CORE_TOKEN, OPERATIONS_TOKEN, WORKER_TOKEN])
def test_no_machine_credential_creates_a_recording(world: World, token: str) -> None:
    response = world.client.post(
        f"/v1/families/{FAMILY_A}/recordings", headers=_token(token), **_upload_kwargs()
    )

    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), SERVICE_PROBES)
def test_a_family_owner_cannot_reach_engineering_tooling(
    world: World, method: str, path: str
) -> None:
    """Trace and replay expose stage timings and evaluation output.

    Owning the family the data describes does not make an operator, so the
    strongest family role is refused here on purpose.
    """

    response = getattr(world.client, method)(path, headers=world.owner_a.headers)

    assert response.status_code == 401


def test_a_family_owner_cannot_replay_their_own_family(world: World) -> None:
    response = world.client.post(f"/v1/families/{FAMILY_A}/replays", headers=world.owner_a.headers)

    assert response.status_code == 401


def test_a_user_cannot_process_a_transcript(world: World) -> None:
    response = world.client.post("/v1/process-transcript", headers=world.owner_a.headers, json={})

    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), [OPERATIONS_PROBE, WORKER_PROBE])
def test_a_user_cannot_reach_operator_or_worker_surfaces(
    world: World, method: str, path: str
) -> None:
    response = getattr(world.client, method)(path, headers=world.owner_a.headers)

    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), SERVICE_PROBES)
def test_the_application_token_still_serves_engineering_tooling(
    world: World, method: str, path: str
) -> None:
    response = getattr(world.client, method)(path, headers=_token(CORE_TOKEN))

    assert response.status_code != 401


@pytest.mark.parametrize("token", [OPERATIONS_TOKEN, WORKER_TOKEN])
@pytest.mark.parametrize(("method", "path"), SERVICE_PROBES)
def test_other_machine_credentials_do_not_reach_service_tooling(
    world: World, token: str, method: str, path: str
) -> None:
    response = getattr(world.client, method)(path, headers=_token(token))

    assert response.status_code == 401


@pytest.mark.parametrize("token", [CORE_TOKEN, WORKER_TOKEN])
def test_only_the_operations_credential_reaches_operator_routes(world: World, token: str) -> None:
    method, path = OPERATIONS_PROBE

    assert getattr(world.client, method)(path, headers=_token(token)).status_code == 401
    assert getattr(world.client, method)(path, headers=_token(OPERATIONS_TOKEN)).status_code != 401


@pytest.mark.parametrize("token", [CORE_TOKEN, OPERATIONS_TOKEN])
def test_only_the_worker_credential_reaches_worker_routes(world: World, token: str) -> None:
    method, path = WORKER_PROBE

    assert getattr(world.client, method)(path, headers=_token(token)).status_code == 401
    assert getattr(world.client, method)(path, headers=_token(WORKER_TOKEN)).status_code != 401


# ------------------------------------------------------------ authentication


def test_a_missing_token_is_distinguished_from_a_rejected_one(world: World) -> None:
    path = f"/v1/families/{FAMILY_A}/recordings/{REC_A}"

    missing = world.client.get(path)
    rejected = world.client.get(path, headers=_token("not-a-real-token"))

    assert missing.status_code == rejected.status_code == 401
    assert missing.json()["error"]["code"] == "authentication_required"
    assert rejected.json()["error"]["code"] == "invalid_token"


def test_public_probes_need_no_credential(world: World) -> None:
    assert world.client.get("/health").status_code == 200
    assert world.client.get("/ready").status_code in (200, 503)


# --------------------------------------------------------- first login rules


def test_a_new_user_gets_no_family_and_sees_no_private_one(world: World) -> None:
    newcomer = world._user("brand-new")

    listed = world.client.get("/v1/families", headers=newcomer.headers)
    private = world.client.get(f"/v1/families/{FAMILY_A}", headers=newcomer.headers)

    assert listed.status_code == 200
    assert listed.json() == []
    assert private.status_code == 404


def test_signing_in_never_creates_an_archive_person(world: World) -> None:
    """A MURA account and a family-tree Person are different domains.

    Nothing about authenticating may mint an evidence-backed archive entity, so
    a fresh principal's user_id must not appear as a person id anywhere.
    """

    newcomer = world._user("person-check")
    profiles = world.client.get(f"/v1/families/{FAMILY_A}/profiles", headers=world.owner_a.headers)

    assert newcomer.user_id.startswith("user_")
    assert newcomer.user_id not in profiles.text
    assert all(profile["person_id"] != newcomer.user_id for profile in profiles.json())


def test_an_upload_does_not_turn_the_uploader_into_a_person(world: World) -> None:
    accepted = world.client.post(
        f"/v1/families/{FAMILY_A}/recordings", headers=world.owner_a.headers, **_upload_kwargs()
    )

    assert accepted.status_code == 202
    result = world.client.get(
        f"/v1/families/{FAMILY_A}/recordings/{accepted.json()['recording_id']}",
        headers=world.owner_a.headers,
    )
    # No pipeline result yet, so the recording is not readable -- but crucially
    # the speaker was never bound to the uploader's account id.
    assert result.status_code in (200, 409)
    assert world.owner_a.user_id not in result.text


# ------------------------------------------------------- dependency caching


def test_one_request_resolves_membership_exactly_once(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FastAPI caches a dependency result per request; this proves we rely on it.

    Every capability guard is built from one shared context dependency, so a
    route carrying several of them must still cost a single membership query.
    """

    calls: list[str] = []
    original = FamilyAuthorizationService.authorize

    def counting(self: FamilyAuthorizationService, principal: Any, family_id: str) -> Any:
        calls.append(family_id)
        return original(self, principal, family_id)

    monkeypatch.setattr(FamilyAuthorizationService, "authorize", counting)

    response = world.client.get(
        f"/v1/families/{FAMILY_A}/recordings/{REC_A}", headers=world.owner_a.headers
    )

    assert response.status_code == 200
    assert calls == [FAMILY_A]


def test_several_capability_guards_share_one_membership_query(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original = FamilyAuthorizationService.authorize

    def counting(self: FamilyAuthorizationService, principal: Any, family_id: str) -> Any:
        calls.append(family_id)
        return original(self, principal, family_id)

    monkeypatch.setattr(FamilyAuthorizationService, "authorize", counting)

    probe = FastAPI()
    probe.dependency_overrides[get_settings] = lambda: world.settings
    probe.dependency_overrides[get_auth_verifier] = lambda: world.verifier
    probe.dependency_overrides[get_family_authorization_service] = lambda: (
        FamilyAuthorizationService(world.database)
    )
    probe.dependency_overrides[get_runtime] = lambda: _Runtime(world.database, Path("."))

    @probe.get(
        "/probe/{family_id}",
        dependencies=[
            Depends(require_read_recordings),
            Depends(require_read_conflicts),
        ],
    )
    def probe_route(family_id: str) -> dict[str, str]:
        return {"family_id": family_id}

    response = TestClient(probe, raise_server_exceptions=False).get(
        f"/probe/{FAMILY_A}", headers=world.owner_a.headers
    )

    assert response.status_code == 200
    assert calls == [FAMILY_A], "two guards must not mean two membership queries"


# ------------------------------------------------------------ real PostgreSQL

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pg_only = pytest.mark.skipif(
    not POSTGRES_URL or "test" not in (POSTGRES_URL or "").rsplit("/", 1)[-1].lower(),
    reason="TEST_POSTGRES_URL pointing at a disposable test database is required",
)


@pytest.fixture
def pg_world(tmp_path: Path) -> Iterator[World]:
    """The same matrix against PostgreSQL, where the constraints are real.

    SQLite does not enforce foreign keys by default and orders rows differently,
    so an isolation bug can survive it. The engine that runs in production is the
    one that has to agree.
    """

    assert POSTGRES_URL is not None
    database = Database(POSTGRES_URL)
    database.create_schema()
    _purge(database)
    try:
        yield World(tmp_path, database=database)
    finally:
        _purge(database)


def _purge(database: Database) -> None:
    """Remove this suite's fixtures; the test database is shared.

    Order matters, and so does breadth. Memberships are cleared for every test
    user rather than only for these two families: the membership foreign key
    RESTRICTs deleting a user, so one stray membership left by another suite
    would block the whole cleanup and make this fixture flaky.
    """

    families = (FAMILY_A, FAMILY_B)
    with database.session_factory.begin() as session:
        # Jobs and results hang off a recording, not a family.
        for by_recording in (PipelineResultRow, ProcessingJobRow):
            session.query(by_recording).filter(
                by_recording.recording_id.in_((REC_A, REC_B))
            ).delete(synchronize_session=False)
        for model in (RecordingRow, MaterializedPersonProfileRow, ArchiveConflictRow):
            session.query(model).filter(model.family_id.in_(families)).delete(
                synchronize_session=False
            )

        test_users = select(UserRow.user_id).where(UserRow.auth_issuer == ISSUER)
        session.query(FamilyMembershipRow).filter(
            FamilyMembershipRow.user_id.in_(test_users)
        ).delete(synchronize_session=False)
        session.query(FamilyMembershipRow).filter(
            FamilyMembershipRow.family_id.in_(families)
        ).delete(synchronize_session=False)
        session.query(FamilyRow).filter(FamilyRow.family_id.in_(families)).delete(
            synchronize_session=False
        )
        session.query(UserRow).filter(UserRow.auth_issuer == ISSUER).delete(
            synchronize_session=False
        )


@pg_only
@pytest.mark.parametrize("role", ["viewer", "editor", "owner"])
def test_postgres_role_matrix_matches_sqlite(pg_world: World, role: str) -> None:
    actor = {
        "viewer": pg_world.viewer_a,
        "editor": pg_world.editor_a,
        "owner": pg_world.owner_a,
    }[role]

    read = pg_world.client.get(f"/v1/families/{FAMILY_A}/recordings/{REC_A}", headers=actor.headers)
    create = pg_world.client.post(
        f"/v1/families/{FAMILY_A}/recordings", headers=actor.headers, **_upload_kwargs()
    )
    administer = pg_world.client.patch(
        f"/v1/families/{FAMILY_A}/members/{pg_world.viewer_a.user_id}",
        headers=actor.headers,
        json={"role": "editor"},
    )

    assert read.status_code == 200
    assert create.status_code == (403 if role == "viewer" else 202)
    assert administer.status_code == (200 if role == "owner" else 403)


@pg_only
@pytest.mark.parametrize(("label", "path"), CROSS_FAMILY_ROUTES)
def test_postgres_resource_isolation_holds(pg_world: World, label: str, path: str) -> None:
    del label
    response = pg_world.client.get(path, headers=pg_world.owner_a.headers)

    assert response.status_code == 404


@pg_only
@pytest.mark.parametrize(("label", "path"), OUTSIDER_ROUTES)
def test_postgres_outsiders_see_nothing(pg_world: World, label: str, path: str) -> None:
    del label
    response = pg_world.client.get(path, headers=pg_world.outsider.headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "family_not_found"


@pg_only
def test_postgres_service_token_cannot_read_family_data(pg_world: World) -> None:
    response = pg_world.client.get(
        f"/v1/families/{FAMILY_A}/recordings/{REC_A}", headers=_token(CORE_TOKEN)
    )

    assert response.status_code == 401


@pg_only
def test_postgres_sole_owner_invariant_holds_over_http(pg_world: World) -> None:
    second = f"/v1/families/{FAMILY_A}/members/{pg_world.second_owner_a.user_id}"
    assert pg_world.client.delete(second, headers=pg_world.owner_a.headers).status_code == 204

    myself = f"/v1/families/{FAMILY_A}/members/{pg_world.owner_a.user_id}"
    response = pg_world.client.delete(myself, headers=pg_world.owner_a.headers)

    assert response.status_code == 409
    assert pg_world.identity.count_owners(FAMILY_A) == 1


@pg_only
def test_postgres_first_login_grants_no_membership(pg_world: World) -> None:
    newcomer = pg_world._user("pg-newcomer")

    listed = pg_world.client.get("/v1/families", headers=newcomer.headers)
    private = pg_world.client.get(f"/v1/families/{FAMILY_A}", headers=newcomer.headers)

    assert listed.json() == []
    assert private.status_code == 404
