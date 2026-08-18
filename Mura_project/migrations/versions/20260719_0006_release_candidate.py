"""Add release control and deterministic replay records.

Revision ID: 20260719_0006
Revises: 20260719_0005
Create Date: 2026-07-19
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260719_0006"
down_revision: str | None = "20260719_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "release_control",
        sa.Column("control_key", sa.String(length=32), nullable=False),
        sa.Column("active_release_id", sa.String(length=96), nullable=False),
        sa.Column("previous_release_id", sa.String(length=96), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("control_key"),
    )
    op.create_index(
        "ix_release_control_active_release_id",
        "release_control",
        ["active_release_id"],
    )
    release_control = sa.table(
        "release_control",
        sa.column("control_key", sa.String(length=32)),
        sa.column("active_release_id", sa.String(length=96)),
        sa.column("previous_release_id", sa.String(length=96)),
        sa.column("generation", sa.Integer()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        release_control,
        [
            {
                "control_key": "global",
                "active_release_id": "mura-core-v1.0.0-rc1",
                "previous_release_id": "mura-core-v0.9.0",
                "generation": 1,
                "updated_at": datetime.now(UTC),
            }
        ],
    )
    op.create_table(
        "release_decisions",
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("from_release_id", sa.String(length=96), nullable=False),
        sa.Column("to_release_id", sa.String(length=96), nullable=False),
        sa.Column("requested_by", sa.String(length=256), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index(
        "ix_release_decisions_action",
        "release_decisions",
        ["action"],
    )
    op.create_index(
        "ix_release_decisions_to_release_id",
        "release_decisions",
        ["to_release_id"],
    )
    op.create_table(
        "pipeline_replay_runs",
        sa.Column("replay_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("release_id", sa.String(length=96), nullable=False),
        sa.Column("protocol_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_recording_count", sa.Integer(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "report_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("replay_id"),
    )
    op.create_index(
        "ix_pipeline_replay_runs_family_id",
        "pipeline_replay_runs",
        ["family_id"],
    )
    op.create_index(
        "ix_pipeline_replay_runs_release_id",
        "pipeline_replay_runs",
        ["release_id"],
    )
    op.create_index(
        "ix_pipeline_replay_runs_status",
        "pipeline_replay_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_pipeline_replay_runs_status", table_name="pipeline_replay_runs")
    op.drop_index("ix_pipeline_replay_runs_release_id", table_name="pipeline_replay_runs")
    op.drop_index("ix_pipeline_replay_runs_family_id", table_name="pipeline_replay_runs")
    op.drop_table("pipeline_replay_runs")
    op.drop_index("ix_release_decisions_to_release_id", table_name="release_decisions")
    op.drop_index("ix_release_decisions_action", table_name="release_decisions")
    op.drop_table("release_decisions")
    op.drop_index("ix_release_control_active_release_id", table_name="release_control")
    op.drop_table("release_control")
