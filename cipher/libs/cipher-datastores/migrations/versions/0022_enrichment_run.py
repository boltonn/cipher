"""Add the `enrichment_run` table.

One row per enrichment workflow invocation: the analytic, the dataset, the
device, how many units it processed, and how long it took. Feeds two things --
median `duration_seconds / unit_count` per (enrichment_type, device) is the
throughput used for request-time estimates, and the rows themselves are a plain
"what ran when" audit log. Written by the orchestration run recorder, distinct
from the queue-level `enrichment` rows. Purely additive.

Revision ID: 0022_enrichment_run
Revises: 0021_dataset_staging
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_enrichment_run"
down_revision: str | None = "0021_dataset_staging"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enrichment_run",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("enrichment_type", sa.String(), nullable=False),
        sa.Column(
            "dataset_id",
            sa.String(),
            sa.ForeignKey("dataset.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("device", sa.String(), nullable=False, server_default="na"),
        sa.Column("unit", sa.String(), nullable=False, server_default="file"),
        sa.Column("unit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("date_started", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("date_completed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
    )
    op.create_index("ix_enrichment_run_enrichment_type", "enrichment_run", ["enrichment_type"])
    op.create_index("ix_enrichment_run_dataset_id", "enrichment_run", ["dataset_id"])
    op.create_index(
        "ix_enrichment_run_type_device_status",
        "enrichment_run",
        ["enrichment_type", "device", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_enrichment_run_type_device_status", table_name="enrichment_run")
    op.drop_index("ix_enrichment_run_dataset_id", table_name="enrichment_run")
    op.drop_index("ix_enrichment_run_enrichment_type", table_name="enrichment_run")
    op.drop_table("enrichment_run")
