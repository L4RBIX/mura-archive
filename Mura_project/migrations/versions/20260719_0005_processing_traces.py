"""Create structured processing trace events.

Revision ID: 20260719_0005
Revises: 20260719_0004
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260719_0005"
down_revision: str | None = "20260719_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processing_trace_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=96), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("recording_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["processing_jobs.job_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.recording_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "trace_id",
            "attempt",
            "sequence",
            name="uq_processing_trace_attempt_sequence",
        ),
    )
    op.create_index(
        "ix_processing_trace_events_trace_id",
        "processing_trace_events",
        ["trace_id"],
    )
    op.create_index(
        "ix_processing_trace_events_job_id",
        "processing_trace_events",
        ["job_id"],
    )
    op.create_index(
        "ix_processing_trace_events_recording_id",
        "processing_trace_events",
        ["recording_id"],
    )
    op.create_index(
        "ix_processing_trace_events_family_id",
        "processing_trace_events",
        ["family_id"],
    )
    op.create_index(
        "ix_processing_trace_events_stage",
        "processing_trace_events",
        ["stage"],
    )
    op.create_index(
        "ix_processing_trace_events_outcome",
        "processing_trace_events",
        ["outcome"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processing_trace_events_outcome",
        table_name="processing_trace_events",
    )
    op.drop_index(
        "ix_processing_trace_events_stage",
        table_name="processing_trace_events",
    )
    op.drop_index(
        "ix_processing_trace_events_family_id",
        table_name="processing_trace_events",
    )
    op.drop_index(
        "ix_processing_trace_events_recording_id",
        table_name="processing_trace_events",
    )
    op.drop_index(
        "ix_processing_trace_events_job_id",
        table_name="processing_trace_events",
    )
    op.drop_index(
        "ix_processing_trace_events_trace_id",
        table_name="processing_trace_events",
    )
    op.drop_table("processing_trace_events")
