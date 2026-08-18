"""Create archive claim ledger and materialized family graph.

Revision ID: 20260719_0002
Revises: 20260718_0001
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260719_0002"
down_revision: str | None = "20260718_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "archive_people",
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("canonical_name", sa.String(length=256), nullable=False),
        sa.Column("normalized_name", sa.String(length=256), nullable=False),
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verified_aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column(
            "relations_to_speakers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "source_recording_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("person_id"),
        sa.UniqueConstraint("family_id", "person_id"),
    )
    op.create_index("ix_archive_people_family_id", "archive_people", ["family_id"])
    op.create_index(
        "ix_archive_people_normalized_name",
        "archive_people",
        ["normalized_name"],
    )

    op.create_table(
        "archive_claims",
        sa.Column("claim_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("recording_id", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("source_object_id", sa.String(length=128), nullable=False),
        sa.Column("predicate", sa.String(length=128), nullable=False),
        sa.Column("subject_person_id", sa.String(length=64), nullable=True),
        sa.Column("object_person_id", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_class", sa.String(length=64), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("assertion_mode", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "derived_from_claim_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.recording_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("claim_id"),
    )
    for column in (
        "family_id",
        "recording_id",
        "object_type",
        "source_object_id",
        "predicate",
        "subject_person_id",
        "object_person_id",
        "evidence_class",
        "verification_status",
        "status",
    ):
        op.create_index(f"ix_archive_claims_{column}", "archive_claims", [column])

    op.create_table(
        "archive_conflicts",
        sa.Column("conflict_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("conflict_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detected_by", sa.String(length=32), nullable=False),
        sa.Column("claim_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preferred_claim_id", sa.String(length=64), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("conflict_id"),
    )
    op.create_index(
        "ix_archive_conflicts_family_id",
        "archive_conflicts",
        ["family_id"],
    )
    op.create_index(
        "ix_archive_conflicts_conflict_type",
        "archive_conflicts",
        ["conflict_type"],
    )
    op.create_index("ix_archive_conflicts_status", "archive_conflicts", ["status"])

    op.create_table(
        "family_graph_edges",
        sa.Column("edge_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("relationship_type", sa.String(length=64), nullable=False),
        sa.Column("subject_person_id", sa.String(length=64), nullable=False),
        sa.Column("subject_role", sa.String(length=64), nullable=False),
        sa.Column("object_person_id", sa.String(length=64), nullable=False),
        sa.Column("object_role", sa.String(length=64), nullable=False),
        sa.Column(
            "source_claim_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("edge_id"),
    )
    for column in (
        "family_id",
        "relationship_type",
        "subject_person_id",
        "object_person_id",
    ):
        op.create_index(f"ix_family_graph_edges_{column}", "family_graph_edges", [column])

    op.create_table(
        "archive_corrections",
        sa.Column("correction_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("recording_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=256), nullable=True),
        sa.Column("original_value", sa.Text(), nullable=False),
        sa.Column("corrected_value", sa.Text(), nullable=False),
        sa.Column(
            "source_segment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.recording_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("correction_id"),
    )
    op.create_index(
        "ix_archive_corrections_family_id",
        "archive_corrections",
        ["family_id"],
    )
    op.create_index(
        "ix_archive_corrections_recording_id",
        "archive_corrections",
        ["recording_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_archive_corrections_recording_id", table_name="archive_corrections")
    op.drop_index("ix_archive_corrections_family_id", table_name="archive_corrections")
    op.drop_table("archive_corrections")

    for column in (
        "object_person_id",
        "subject_person_id",
        "relationship_type",
        "family_id",
    ):
        op.drop_index(f"ix_family_graph_edges_{column}", table_name="family_graph_edges")
    op.drop_table("family_graph_edges")

    op.drop_index("ix_archive_conflicts_status", table_name="archive_conflicts")
    op.drop_index("ix_archive_conflicts_conflict_type", table_name="archive_conflicts")
    op.drop_index("ix_archive_conflicts_family_id", table_name="archive_conflicts")
    op.drop_table("archive_conflicts")

    for column in (
        "status",
        "verification_status",
        "evidence_class",
        "object_person_id",
        "subject_person_id",
        "predicate",
        "source_object_id",
        "object_type",
        "recording_id",
        "family_id",
    ):
        op.drop_index(f"ix_archive_claims_{column}", table_name="archive_claims")
    op.drop_table("archive_claims")

    op.drop_index("ix_archive_people_normalized_name", table_name="archive_people")
    op.drop_index("ix_archive_people_family_id", table_name="archive_people")
    op.drop_table("archive_people")
