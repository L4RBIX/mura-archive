"""Persist requested recording language intent.

Revision ID: 20260719_0007
Revises: 20260719_0006
Create Date: 2026-08-17

Both columns are nullable only so existing rows migrate without a backfill.
Recordings created through the canonical API always persist explicit values;
the application reads NULL as AudioLanguage.AUTO / OutputLanguage.SAME_AS_TRANSCRIPT.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0007"
down_revision: str | None = "20260719_0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("recordings", sa.Column("audio_language", sa.String(length=32), nullable=True))
    op.add_column("recordings", sa.Column("output_language", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("recordings", "output_language")
    op.drop_column("recordings", "audio_language")
