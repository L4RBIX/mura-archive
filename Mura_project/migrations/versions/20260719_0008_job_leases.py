"""Durable job lease ownership.

Revision ID: 20260719_0008
Revises: 20260719_0007
Create Date: 2026-08-17

All columns are nullable so existing rows migrate without a backfill: a NULL
lease reads as "no worker owns this job", which is exactly right for historical
queued or half-processed rows and leaves them immediately reclaimable.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0008"
down_revision: str | None = "20260719_0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("lease_owner", sa.String(length=64), nullable=True))
    op.add_column(
        "processing_jobs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The claim query filters on both, on every poll from every worker.
    op.create_index(
        "ix_processing_jobs_lease_owner",
        "processing_jobs",
        ["lease_owner"],
    )
    op.create_index(
        "ix_processing_jobs_lease_expires_at",
        "processing_jobs",
        ["lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_lease_expires_at", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_lease_owner", table_name="processing_jobs")
    op.drop_column("processing_jobs", "last_heartbeat_at")
    op.drop_column("processing_jobs", "lease_expires_at")
    op.drop_column("processing_jobs", "claimed_at")
    op.drop_column("processing_jobs", "lease_owner")
