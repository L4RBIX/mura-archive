"""Every route must declare which credential guards it, and actually use it.

Two jobs. First, prove the classification registry matches the live API surface,
so a new endpoint cannot ship without an auth class. Second, prove the wiring
matches the declaration: the assertions below read guards off the real dependency
graph, so an alias, a factory-built closure or a guard nested two levels down is
still seen, and a route that merely *looks* protected cannot pass.

PR-03B-SWITCH moved every family application route onto the Principal chain, so
the pending-switch checklist is now asserted empty rather than asserted intact.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.api.main import create_app
from mura.config import CoreSettings
from mura.identity.route_classification import (
    CAPABILITY_BY_ROUTE,
    PENDING_SWITCH_TO_PRINCIPAL,
    PRINCIPAL_NATIVE,
    ROUTE_AUTH_CLASSES,
    AuthClass,
    classify,
    routes_in,
)
from tests.route_introspection import (
    CAPABILITY_GUARD,
    CORE_TOKEN_GUARD,
    OPERATIONS_TOKEN_GUARD,
    PRINCIPAL_GUARD,
    SERVICE_GUARDS,
    WORKER_TOKEN_GUARD,
    guards_by_path,
    live_paths,
    paths_requiring,
)


def _settings(**overrides: Any) -> CoreSettings:
    payload: dict[str, Any] = {
        "DEEPSEEK_API_KEY": "sk-" + "d" * 40,
        "CORE_API_KEY": "c" * 40,
        "OPERATIONS_API_KEY": "o" * 40,
        "WORKER_REGISTRATION_TOKEN": "r" * 40,
        "KAGGLE_ASR_API_KEY": "a" * 40,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    }
    payload.update(overrides)
    return CoreSettings.model_validate(payload)


@pytest.fixture(scope="module")
def application() -> Any:
    return create_app(_settings())


# ------------------------------------------------------------- the registry


def test_every_live_route_has_exactly_one_auth_class(application: Any) -> None:
    unclassified = sorted(path for path in live_paths(application) if classify(path) is None)

    assert unclassified == [], "every route must declare an auth class in route_classification.py"


def test_the_registry_does_not_describe_routes_that_no_longer_exist(application: Any) -> None:
    stale = sorted(set(ROUTE_AUTH_CLASSES) - live_paths(application))

    assert stale == []


def test_route_introspection_sees_the_whole_surface(application: Any) -> None:
    """Guard against a silently shallow walk.

    Routes mounted through include_router are nested rather than flattened. If
    this traversal regressed, every assertion below would pass vacuously for
    them, so the infrastructure itself is pinned first.
    """

    paths = live_paths(application)

    assert "/health" in paths
    assert "/v1/capabilities" in paths
    assert "/v1/process-transcript" in paths
    assert "/v1/workers/register" in paths
    assert len(paths) == len(ROUTE_AUTH_CLASSES)


def test_expected_routes_land_in_expected_classes() -> None:
    assert routes_in(AuthClass.PUBLIC_INFRA) == {"/health", "/ready"}
    assert routes_in(AuthClass.WORKER) == {"/v1/workers/register", "/v1/workers/current"}
    assert routes_in(AuthClass.OPERATIONS) == {
        "/v1/operations/release",
        "/v1/operations/release/activate",
        "/v1/operations/release/rollback",
        "/v1/operations/retention",
        "/v1/operations/retention/apply",
    }
    assert routes_in(AuthClass.SERVICE_INTERNAL) == {
        "/v1/process-transcript",
        "/v1/jobs/{job_id}/trace",
        "/v1/families/{family_id}/replays",
    }


def test_replay_is_service_internal_not_family_data() -> None:
    # Deterministic replay is release/evaluation tooling. Family membership must
    # never grant it, so it is deliberately not USER_APP.
    assert classify("/v1/families/{family_id}/replays") is AuthClass.SERVICE_INTERNAL


# ------------------------------------------------ the switch actually happened


def test_no_user_app_route_is_still_pending() -> None:
    """The atomic-switch guarantee, after the switch."""

    assert PENDING_SWITCH_TO_PRINCIPAL == frozenset()


def test_every_user_app_route_is_principal_native() -> None:
    assert PRINCIPAL_NATIVE == routes_in(AuthClass.USER_APP)


@pytest.mark.parametrize("path", sorted(routes_in(AuthClass.USER_APP)))
def test_user_app_routes_authenticate_a_user(application: Any, path: str) -> None:
    assert PRINCIPAL_GUARD in guards_by_path(application)[path]


@pytest.mark.parametrize("path", sorted(CAPABILITY_BY_ROUTE))
def test_family_scoped_routes_enforce_a_capability(application: Any, path: str) -> None:
    """A family-scoped route must check membership, not merely authentication."""

    assert "{family_id}" in path
    assert CAPABILITY_GUARD in guards_by_path(application)[path]


def test_only_family_scoped_user_routes_declare_a_capability(application: Any) -> None:
    capability_paths = paths_requiring(application, CAPABILITY_GUARD)

    assert capability_paths == set(CAPABILITY_BY_ROUTE)


# ----------------------------------------------------- static credential walls


def test_no_user_app_route_accepts_any_service_credential(application: Any) -> None:
    """The core assertion of PR-03B-SWITCH.

    Not just CORE_API_KEY: no user-facing route may be reachable with any of the
    three machine credentials, and none may offer one as a fallback.
    """

    guards = guards_by_path(application)
    leaked = {
        path: sorted(guards[path] & SERVICE_GUARDS)
        for path in routes_in(AuthClass.USER_APP)
        if guards[path] & SERVICE_GUARDS
    }

    assert leaked == {}, f"user routes must not accept a service credential: {leaked}"


def test_no_service_internal_route_accepts_a_user_principal(application: Any) -> None:
    guards = guards_by_path(application)
    leaked = {
        path
        for path in routes_in(AuthClass.SERVICE_INTERNAL)
        if PRINCIPAL_GUARD in guards[path] or CAPABILITY_GUARD in guards[path]
    }

    assert leaked == set(), f"engineering tooling must not be reachable by a family role: {leaked}"


@pytest.mark.parametrize("path", sorted(routes_in(AuthClass.SERVICE_INTERNAL)))
def test_service_internal_routes_require_the_application_token(application: Any, path: str) -> None:
    guards = guards_by_path(application)[path]

    assert CORE_TOKEN_GUARD in guards
    assert not guards & {OPERATIONS_TOKEN_GUARD, WORKER_TOKEN_GUARD}


@pytest.mark.parametrize("path", sorted(routes_in(AuthClass.OPERATIONS)))
def test_operations_routes_require_only_the_operations_token(application: Any, path: str) -> None:
    guards = guards_by_path(application)[path]

    assert OPERATIONS_TOKEN_GUARD in guards
    assert not guards & {CORE_TOKEN_GUARD, WORKER_TOKEN_GUARD, PRINCIPAL_GUARD, CAPABILITY_GUARD}


@pytest.mark.parametrize("path", sorted(routes_in(AuthClass.WORKER)))
def test_worker_routes_require_only_the_worker_token(application: Any, path: str) -> None:
    guards = guards_by_path(application)[path]

    assert WORKER_TOKEN_GUARD in guards
    assert not guards & {
        CORE_TOKEN_GUARD,
        OPERATIONS_TOKEN_GUARD,
        PRINCIPAL_GUARD,
        CAPABILITY_GUARD,
    }


@pytest.mark.parametrize("path", sorted(routes_in(AuthClass.PUBLIC_INFRA)))
def test_probes_carry_no_credential_guard(application: Any, path: str) -> None:
    guards = guards_by_path(application)[path]

    assert not guards & (SERVICE_GUARDS | {PRINCIPAL_GUARD, CAPABILITY_GUARD})


def test_the_application_token_reaches_nothing_but_service_internal(application: Any) -> None:
    assert paths_requiring(application, CORE_TOKEN_GUARD) == routes_in(AuthClass.SERVICE_INTERNAL)


def test_route_source_contains_no_credential_fallback() -> None:
    """A sanity check in source text, since introspection cannot see intent.

    Dependency graphs show what a route requires, not what a handler might do
    with a second credential inside its body. `or`-ing two guards together is the
    shape that would produce exactly that, so it is spelled out as forbidden.
    """

    from pathlib import Path

    forbidden = ("core_token_dependency or", "or core_token_dependency", "or require_core_token")
    offenders = [
        f"{path.name}: {needle}"
        for path in sorted(Path("apps/api").glob("*.py"))
        for needle in forbidden
        if needle in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
