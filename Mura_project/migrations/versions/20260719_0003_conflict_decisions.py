"""Create conflict decision audit history.

Revision ID: 20260719_0003
Revises: 20260719_0002
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260719_0003"
down_revision: str | None = "20260719_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "archive_conflict_decisions",
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("conflict_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("resulting_status", sa.String(length=32), nullable=False),
        sa.Column("preferred_claim_id", sa.String(length=64), nullable=True),
        sa.Column("reviewer_reference", sa.String(length=256), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conflict_id"],
            ["archive_conflicts.conflict_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index(
        "ix_archive_conflict_decisions_conflict_id",
        "archive_conflict_decisions",
        ["conflict_id"],
    )
    op.create_index(
        "ix_archive_conflict_decisions_family_id",
        "archive_conflict_decisions",
        ["family_id"],
    )
    op.create_index(
        "ix_archive_conflict_decisions_action",
        "archive_conflict_decisions",
        ["action"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_archive_conflict_decisions_action",
        table_name="archive_conflict_decisions",
    )
    op.drop_index(
        "ix_archive_conflict_decisions_family_id",
        table_name="archive_conflict_decisions",
    )
    op.drop_index(
        "ix_archive_conflict_decisions_conflict_id",
        table_name="archive_conflict_decisions",
    )
    op.drop_table("archive_conflict_decisions")
