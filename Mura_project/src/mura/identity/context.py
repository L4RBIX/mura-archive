"""Request-scoped family authorization.

One question, answered once per request: does this principal belong to this
family, and in what role? Everything downstream asks the resulting context for a
capability rather than comparing role strings.

Membership resolution is a single join rather than three lookups, and it relies
on the `uq_family_membership` unique constraint plus the family/user indexes
added in migration 0010.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from mura.identity.auth import Principal
from mura.identity.policy import Capability, FamilyRole, capabilities_for, role_allows
from mura.storage.database import Database
from mura.storage.identity import FamilyMembershipRow, FamilyRow


class FamilyAccessDenied(Exception):
    """The principal is not a member of the requested family.

    Deliberately does not distinguish "no such family" from "not your family":
    both must look identical to a caller, so neither confirms that a private
    family exists.
    """


class InsufficientFamilyRole(Exception):
    """A member of the family lacks the capability the route requires."""

    def __init__(self, capability: Capability) -> None:
        super().__init__(f"missing capability: {capability.value}")
        self.capability = capability


@dataclass(frozen=True)
class AuthorizedFamilyContext:
    """Proof that this principal may act in this family, and how far."""

    principal: Principal
    family: FamilyRow
    membership: FamilyMembershipRow
    role: FamilyRole

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def family_id(self) -> str:
        return self.family.family_id

    def allows(self, capability: Capability) -> bool:
        return role_allows(self.role, capability)

    def require(self, capability: Capability) -> None:
        """Raise unless the role carries the capability."""

        if not self.allows(capability):
            raise InsufficientFamilyRole(capability)

    @property
    def capabilities(self) -> frozenset[Capability]:
        return capabilities_for(self.role)


class FamilyAuthorizationService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def authorize(self, principal: Principal, family_id: str) -> AuthorizedFamilyContext:
        """Resolve family and membership together, or deny."""

        with self.database.session_factory() as session:
            row = session.execute(
                select(FamilyRow, FamilyMembershipRow)
                .join(
                    FamilyMembershipRow,
                    FamilyMembershipRow.family_id == FamilyRow.family_id,
                )
                .where(
                    FamilyRow.family_id == family_id,
                    FamilyMembershipRow.user_id == principal.user_id,
                )
            ).first()
        if row is None:
            # Covers both "family absent" and "not a member" on purpose.
            raise FamilyAccessDenied(family_id)
        family, membership = row
        return AuthorizedFamilyContext(
            principal=principal,
            family=family,
            membership=membership,
            role=FamilyRole(membership.role),
        )
