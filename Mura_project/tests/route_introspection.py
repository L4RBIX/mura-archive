"""Read the credential wiring straight off the live FastAPI app.

Security assertions here must not be satisfiable by grep. A route's guard can be
an alias, a closure built by a factory, or a dependency of a dependency, and
source text shows none of that; the dependency graph does.

Two traversals are needed. Routes mounted with ``include_router`` are wrapped in
a router object rather than flattened into ``app.routes``, so a shallow scan
silently reports nothing for them -- which is the worst possible failure mode for
a test whose job is to prove a route *is* guarded. And a guard may sit several
levels down a dependency tree, so the tree is walked to the bottom.
"""

from __future__ import annotations

from typing import Any

#: Guards that authenticate the caller, as opposed to authorizing a family.
#: ``require_capability`` is the closure ``build_capability_dependency`` returns,
#: so it names the whole family-authorization chain regardless of capability.
CORE_TOKEN_GUARD = "require_core_token"
OPERATIONS_TOKEN_GUARD = "require_operations_token"
WORKER_TOKEN_GUARD = "require_worker_token"
PRINCIPAL_GUARD = "get_principal"
CAPABILITY_GUARD = "require_capability"

SERVICE_GUARDS = frozenset({CORE_TOKEN_GUARD, OPERATIONS_TOKEN_GUARD, WORKER_TOKEN_GUARD})


def iter_api_routes(application: Any) -> list[Any]:
    """Every route with a dependency tree, including included routers."""

    found: list[Any] = []
    seen: set[int] = set()

    def walk(routes: Any) -> None:
        for route in routes:
            if id(route) in seen:
                continue
            seen.add(id(route))
            if getattr(route, "path", None) is not None and hasattr(route, "dependant"):
                found.append(route)
            nested = getattr(route, "original_router", None)
            if nested is not None:
                walk(getattr(nested, "routes", []))
            elif hasattr(route, "routes"):
                walk(route.routes)

    walk(application.routes)
    return found


def dependency_names(dependant: Any) -> set[str]:
    """Every callable name in a route's dependency tree, at any depth."""

    names: set[str] = set()
    for sub in getattr(dependant, "dependencies", []):
        call = getattr(sub, "call", None)
        if call is not None:
            names.add(getattr(call, "__name__", ""))
        names |= dependency_names(sub)
    return names


def guards_by_path(application: Any) -> dict[str, set[str]]:
    """Path template -> the union of guard names across its methods."""

    guards: dict[str, set[str]] = {}
    for route in iter_api_routes(application):
        guards.setdefault(route.path, set()).update(dependency_names(route.dependant))
    return guards


def live_paths(application: Any) -> set[str]:
    return set(guards_by_path(application))


def paths_requiring(application: Any, dependency_name: str) -> set[str]:
    return {path for path, names in guards_by_path(application).items() if dependency_name in names}
