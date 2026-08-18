"""Users, families and memberships.

Revision ID: 20260719_0010
Revises: 20260719_0009
Create Date: 2026-08-17

Historical rows already carry family_id strings across ten tables. The backfill
below creates a FamilyRow for every distinct historical value it finds, keeping
the original identifier so existing recordings and archive data stay addressable.

Those legacy families deliberately get no owner and no membership: inventing one
would hand somebody else's archive to whoever migrated first. They exist so
future foreign keys are satisfiable, and stay invisible to ordinary family
listing until an explicit claim process assigns ownership.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0010"
down_revision: str | None = "20260719_0009"
branch_labels: str | None = None
depends_on: str | None = None

#: Every table known to carry a historical family_id.
_FAMILY_ID_TABLES = (
    "recordings",
    "archive_people",
    "archive_claims",
    "archive_conflicts",
    "archive_conflict_decisions",
    "archive_corrections",
    "family_graph_edges",
    "materialized_person_profiles",
    "pipeline_replay_runs",
    "processing_trace_events",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("auth_issuer", sa.String(length=512), nullable=False),
        sa.Column("auth_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("auth_issuer", "auth_subject", name="uq_users_issuer_subject"),
    )
    op.create_index("ix_users_auth_issuer", "users", ["auth_issuer"])

    op.create_table(
        "families",
        sa.Column("family_id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        # Nullable so a backfilled legacy family has no invented owner.
        sa.Column(
            "created_by_user_id",
            sa.String(length=64),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "family_memberships",
        sa.Column("membership_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "family_id",
            sa.String(length=128),
            sa.ForeignKey("families.family_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # RESTRICT: deleting a user must never cascade into family archive data.
        sa.Column(
            "user_id",
            sa.String(length=64),
            sa.ForeignKey("users.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("family_id", "user_id", name="uq_family_membership"),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')", name="ck_family_membership_role"
        ),
    )
    op.create_index("ix_family_memberships_family_id", "family_memberships", ["family_id"])
    op.create_index("ix_family_memberships_user_id", "family_memberships", ["user_id"])

    _backfill_legacy_families()


def _backfill_legacy_families() -> None:
    """Create a FamilyRow for every distinct historical family_id in use."""

    connection = op.get_bind()
    inspector = sa.inspect(connection)
    present = set(inspector.get_table_names())

    discovered: set[str] = set()
    for table in _FAMILY_ID_TABLES:
        if table not in present:
            continue
        rows = connection.execute(
            sa.text(f'SELECT DISTINCT family_id FROM "{table}" WHERE family_id IS NOT NULL')
        ).scalars()
        discovered.update(value for value in rows if value)

    if not discovered:
        return

    now = sa.func.now()
    for family_id in sorted(discovered):
        connection.execute(
            sa.text(
                """
                INSERT INTO families (family_id, name, created_by_user_id,
                                      created_at, updated_at)
                VALUES (:family_id, :name, NULL, :created_at, :updated_at)
                """
            ).bindparams(
                family_id=family_id,
                # Identifiable as pre-authentication data without inventing a name.
                name=f"Legacy family {family_id}",
                created_at=connection.scalar(sa.select(now)),
                updated_at=connection.scalar(sa.select(now)),
            )
        )


def downgrade() -> None:
    op.drop_index("ix_family_memberships_user_id", table_name="family_memberships")
    op.drop_index("ix_family_memberships_family_id", table_name="family_memberships")
    op.drop_table("family_memberships")
    op.drop_table("families")
    op.drop_index("ix_users_auth_issuer", table_name="users")
    op.drop_table("users")
