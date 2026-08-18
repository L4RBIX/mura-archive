"""One place that decides what a family role may do.

Capabilities rather than role comparisons: routes ask for a capability, and this
table answers. PR-03B applies it mechanically across the existing family routes,
which only works if the decision lives in exactly one place.
"""

from __future__ import annotations

from enum import StrEnum


class FamilyRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class Capability(StrEnum):
    READ_FAMILY = "read_family"
    READ_RECORDINGS = "read_recordings"
    READ_JOBS = "read_jobs"
    READ_REVIEW = "read_review"
    READ_PROFILES = "read_profiles"
    READ_CONFLICTS = "read_conflicts"
    READ_MEMBERS = "read_members"

    CREATE_RECORDING = "create_recording"
    RESOLVE_CONFLICTS = "resolve_conflicts"

    UPDATE_FAMILY = "update_family"
    MANAGE_MEMBERS = "manage_members"


_VIEWER: frozenset[Capability] = frozenset(
    {
        Capability.READ_FAMILY,
        Capability.READ_RECORDINGS,
        Capability.READ_JOBS,
        Capability.READ_REVIEW,
        Capability.READ_PROFILES,
        Capability.READ_CONFLICTS,
        Capability.READ_MEMBERS,
    }
)

#: An editor adds archive mutation but never governance.
_EDITOR: frozenset[Capability] = _VIEWER | {
    Capability.CREATE_RECORDING,
    Capability.RESOLVE_CONFLICTS,
}

#: An owner adds governance: family metadata and membership.
_OWNER: frozenset[Capability] = _EDITOR | {
    Capability.UPDATE_FAMILY,
    Capability.MANAGE_MEMBERS,
}

CAPABILITIES_BY_ROLE: dict[FamilyRole, frozenset[Capability]] = {
    FamilyRole.VIEWER: _VIEWER,
    FamilyRole.EDITOR: _EDITOR,
    FamilyRole.OWNER: _OWNER,
}


def role_allows(role: FamilyRole, capability: Capability) -> bool:
    return capability in CAPABILITIES_BY_ROLE[role]


def capabilities_for(role: FamilyRole) -> frozenset[Capability]:
    return CAPABILITIES_BY_ROLE[role]
