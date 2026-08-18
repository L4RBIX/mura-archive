"""Create materialized person profiles.

Revision ID: 20260719_0004
Revises: 20260719_0003
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260719_0004"
down_revision: str | None = "20260719_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "materialized_person_profiles",
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("canonical_name", sa.String(length=256), nullable=False),
        sa.Column(
            "profile_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "source_claim_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("person_id"),
    )
    op.create_index(
        "ix_materialized_person_profiles_family_id",
        "materialized_person_profiles",
        ["family_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_materialized_person_profiles_family_id",
        table_name="materialized_person_profiles",
    )
    op.drop_table("materialized_person_profiles")
