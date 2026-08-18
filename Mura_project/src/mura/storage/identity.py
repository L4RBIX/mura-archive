"""Users, families and memberships.

A MURA user is an account. A family-tree Person is an evidence-backed archive
entity. They are separate domains and this module never bridges them: signing in
creates a UserRow and nothing else.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from mura.identity.auth import Principal, VerifiedIdentity
from mura.identity.policy import FamilyRole
from mura.storage.database import Base, Database, utcnow


class SoleOwnerError(RuntimeError):
    """Refused: the change would leave the family with no owner."""


class MembershipNotFoundError(LookupError):
    pass


def new_user_id() -> str:
    return f"user_{uuid.uuid4().hex}"


def new_family_id() -> str:
    return f"family_{uuid.uuid4().hex}"


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Identity is issuer+subject, never email: the same address at two
        # providers is two accounts, and must never silently merge.
        UniqueConstraint("auth_issuer", "auth_subject", name="uq_users_issuer_subject"),
    )

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    auth_issuer: Mapped[str] = mapped_column(String(512), index=True)
    auth_subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class FamilyRow(Base):
    __tablename__ = "families"

    family_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    #: Nullable so legacy families backfilled from historical data have no
    #: invented owner. They stay inaccessible until deliberately claimed.
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class FamilyMembershipRow(Base):
    __tablename__ = "family_memberships"
    __table_args__ = (
        UniqueConstraint("family_id", "user_id", name="uq_family_membership"),
        CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="ck_family_membership_role"),
    )

    membership_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("families.family_id", ondelete="CASCADE"), index=True
    )
    #: Deleting a user must never cascade into family archive history, so this
    #: FK restricts rather than cascades; account lifecycle is later work.
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class IdentityRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    # ------------------------------------------------------------------ users

    def resolve_principal(self, identity: VerifiedIdentity) -> Principal:
        """Find or create the internal user for a verified identity.

        Concurrent first logins are handled by the unique constraint rather than
        by a check-then-insert race: if the insert loses, the winner is re-read.
        """

        with self.database.session_factory.begin() as session:
            existing = session.scalar(
                select(UserRow).where(
                    UserRow.auth_issuer == identity.issuer,
                    UserRow.auth_subject == identity.subject,
                )
            )
            if existing is not None:
                # Profile metadata refreshes; nothing privileged is touched.
                existing.email = identity.email or existing.email
                existing.display_name = identity.display_name or existing.display_name
                return _principal(existing)

        try:
            with self.database.session_factory.begin() as session:
                created = UserRow(
                    user_id=new_user_id(),
                    auth_issuer=identity.issuer,
                    auth_subject=identity.subject,
                    email=identity.email,
                    display_name=identity.display_name,
                )
                session.add(created)
                session.flush()
                return _principal(created)
        except IntegrityError:
            # Another request created the same identity first; adopt it.
            with self.database.session_factory() as session:
                winner = session.scalar(
                    select(UserRow).where(
                        UserRow.auth_issuer == identity.issuer,
                        UserRow.auth_subject == identity.subject,
                    )
                )
                if winner is None:
                    raise
                return _principal(winner)

    def get_user(self, user_id: str) -> UserRow | None:
        with self.database.session_factory() as session:
            return session.get(UserRow, user_id)

    # --------------------------------------------------------------- families

    def create_family(self, *, name: str, owner_user_id: str) -> FamilyRow:
        """Create a family and its owner membership in one transaction.

        There is no window in which a family exists without an owner.
        """

        with self.database.session_factory.begin() as session:
            family = FamilyRow(
                family_id=new_family_id(),
                name=name,
                created_by_user_id=owner_user_id,
            )
            session.add(family)
            session.flush()
            session.add(
                FamilyMembershipRow(
                    membership_id=f"membership_{uuid.uuid4().hex}",
                    family_id=family.family_id,
                    user_id=owner_user_id,
                    role=FamilyRole.OWNER.value,
                )
            )
            session.flush()
            session.expunge(family)
            return family

    def list_families_for_user(self, user_id: str) -> list[tuple[FamilyRow, FamilyRole]]:
        """Only families the user belongs to. Legacy families have no members."""

        with self.database.session_factory() as session:
            rows = session.execute(
                select(FamilyRow, FamilyMembershipRow.role)
                .join(
                    FamilyMembershipRow,
                    FamilyMembershipRow.family_id == FamilyRow.family_id,
                )
                .where(FamilyMembershipRow.user_id == user_id)
                .order_by(FamilyRow.created_at)
            ).all()
            return [(family, FamilyRole(role)) for family, role in rows]

    def get_membership(self, *, family_id: str, user_id: str) -> FamilyMembershipRow | None:
        with self.database.session_factory() as session:
            return session.scalar(
                select(FamilyMembershipRow).where(
                    FamilyMembershipRow.family_id == family_id,
                    FamilyMembershipRow.user_id == user_id,
                )
            )

    def get_family_for_member(self, *, family_id: str, user_id: str) -> FamilyRow | None:
        """A non-member sees nothing, which the route turns into 404."""

        with self.database.session_factory() as session:
            return session.scalar(
                select(FamilyRow)
                .join(
                    FamilyMembershipRow,
                    FamilyMembershipRow.family_id == FamilyRow.family_id,
                )
                .where(
                    FamilyRow.family_id == family_id,
                    FamilyMembershipRow.user_id == user_id,
                )
            )

    def list_members(self, family_id: str) -> list[tuple[FamilyMembershipRow, UserRow]]:
        with self.database.session_factory() as session:
            rows = session.execute(
                select(FamilyMembershipRow, UserRow)
                .join(UserRow, UserRow.user_id == FamilyMembershipRow.user_id)
                .where(FamilyMembershipRow.family_id == family_id)
                .order_by(FamilyMembershipRow.created_at)
            ).all()
            return [(membership, user) for membership, user in rows]

    # ------------------------------------------------------- owner invariants

    def _lock_owners(self, session: object, family_id: str) -> int:
        """Count owners while holding their rows, so a race cannot pass twice.

        Two owners demoting themselves concurrently would both read "2 owners"
        and both succeed if the count were unlocked. FOR UPDATE serialises them.
        """

        return len(
            session.scalars(  # type: ignore[attr-defined]
                select(FamilyMembershipRow.membership_id)
                .where(
                    FamilyMembershipRow.family_id == family_id,
                    FamilyMembershipRow.role == FamilyRole.OWNER.value,
                )
                .with_for_update()
            ).all()
        )

    def change_member_role(
        self, *, family_id: str, user_id: str, role: FamilyRole
    ) -> FamilyMembershipRow:
        with self.database.session_factory.begin() as session:
            owners = self._lock_owners(session, family_id)
            membership = session.scalar(
                select(FamilyMembershipRow)
                .where(
                    FamilyMembershipRow.family_id == family_id,
                    FamilyMembershipRow.user_id == user_id,
                )
                .with_for_update()
            )
            if membership is None:
                raise MembershipNotFoundError(user_id)
            demoting_owner = (
                membership.role == FamilyRole.OWNER.value and role is not FamilyRole.OWNER
            )
            if demoting_owner and owners <= 1:
                raise SoleOwnerError("a family must always retain at least one owner")
            membership.role = role.value
            membership.updated_at = utcnow()
            session.flush()
            session.expunge(membership)
            return membership

    def remove_member(self, *, family_id: str, user_id: str) -> None:
        with self.database.session_factory.begin() as session:
            owners = self._lock_owners(session, family_id)
            membership = session.scalar(
                select(FamilyMembershipRow)
                .where(
                    FamilyMembershipRow.family_id == family_id,
                    FamilyMembershipRow.user_id == user_id,
                )
                .with_for_update()
            )
            if membership is None:
                raise MembershipNotFoundError(user_id)
            if membership.role == FamilyRole.OWNER.value and owners <= 1:
                raise SoleOwnerError("a family must always retain at least one owner")
            session.delete(membership)

    def count_owners(self, family_id: str) -> int:
        with self.database.session_factory() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(FamilyMembershipRow)
                    .where(
                        FamilyMembershipRow.family_id == family_id,
                        FamilyMembershipRow.role == FamilyRole.OWNER.value,
                    )
                )
                or 0
            )


def _principal(user: UserRow) -> Principal:
    return Principal(
        user_id=user.user_id,
        issuer=user.auth_issuer,
        subject=user.auth_subject,
        email=user.email,
        display_name=user.display_name,
    )
