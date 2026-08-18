"""Durable audio storage metadata.

Revision ID: 20260719_0009
Revises: 20260719_0008
Create Date: 2026-08-17

Purely additive. audio_path is deliberately kept so recordings created before
storage keys existed remain readable: a NULL storage_key with a populated
audio_path identifies a legacy local recording. Canonical recordings created
through the API always populate storage_key.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0009"
down_revision: str | None = "20260719_0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("recordings", sa.Column("storage_key", sa.Text(), nullable=True))
    op.add_column("recordings", sa.Column("storage_backend", sa.String(length=32), nullable=True))
    op.add_column("recordings", sa.Column("audio_sha256", sa.String(length=64), nullable=True))
    op.add_column("recordings", sa.Column("audio_size_bytes", sa.Integer(), nullable=True))
    op.add_column("recordings", sa.Column("audio_mime_type", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("recordings", "audio_mime_type")
    op.drop_column("recordings", "audio_size_bytes")
    op.drop_column("recordings", "audio_sha256")
    op.drop_column("recordings", "storage_backend")
    op.drop_column("recordings", "storage_key")
