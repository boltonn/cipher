"""Run plans on `enrichment_run` + which run claimed each `enrichment` row (docs/pipeline-runner.md).

A plan step is an `enrichment_run` row created `requested` / `queued` with a `plan_id`; a
`cipher worker` claims it and keeps `date_heartbeat` fresh while it runs. `enrichment.run_id`
lets a dead run's claimed files go straight back to the queue.

Also fixes `idx_enrichment_pending`: its predicate used lowercase statuses, but the column
stores enum names (`PENDING`), so the index never matched.

Revision ID: 0055_run_plans
Revises: 0054_attachment_found_at_paths
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "0055_run_plans"
down_revision: str | None = "0054_attachment_found_at_paths"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN_COLUMNS = (
    sa.Column("plan_id", sa.String(), nullable=True),
    sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("depends_on", ARRAY(sa.String()), nullable=False, server_default="{}"),
    sa.Column("pool", sa.String(), nullable=True),
    sa.Column("services", ARRAY(sa.String()), nullable=False, server_default="{}"),
    sa.Column("worker", sa.String(), nullable=True),
    sa.Column("note", sa.Text(), nullable=True),
    sa.Column("requested_by", sa.String(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    sa.Column("approved_by", sa.String(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    sa.Column("code_version", JSONB(), nullable=True),
    sa.Column("date_created", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    sa.Column("date_approved", sa.DateTime(timezone=True), nullable=True),
    sa.Column("date_heartbeat", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    """Add the plan columns, `enrichment.run_id`, and fix the pending index."""
    for column in _RUN_COLUMNS:
        op.add_column("enrichment_run", column)
    op.execute("UPDATE enrichment_run SET date_created = date_started")
    op.create_index("ix_enrichment_run_plan_id", "enrichment_run", ["plan_id"])
    op.create_index(
        "ix_enrichment_run_waiting",
        "enrichment_run",
        ["pool", "date_created"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.add_column(
        "enrichment",
        sa.Column("run_id", sa.String(), sa.ForeignKey("enrichment_run.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index(
        "ix_enrichment_processing_run", "enrichment", ["run_id"], postgresql_where=sa.text("status = 'PROCESSING'")
    )
    op.drop_index("idx_enrichment_pending", table_name="enrichment")
    op.create_index(
        "idx_enrichment_pending",
        "enrichment",
        ["enrichment_type", "enrichable_type", "date_created"],
        postgresql_where=sa.text("status IN ('PENDING', 'FAILED')"),
    )


def downgrade() -> None:
    """Drop the plan columns and `enrichment.run_id`; restore the old pending index."""
    op.drop_index("idx_enrichment_pending", table_name="enrichment")
    op.create_index(
        "idx_enrichment_pending",
        "enrichment",
        ["enrichment_type", "enrichable_type", "date_created"],
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )
    op.drop_index("ix_enrichment_processing_run", table_name="enrichment")
    op.drop_column("enrichment", "run_id")
    op.drop_index("ix_enrichment_run_waiting", table_name="enrichment_run")
    op.drop_index("ix_enrichment_run_plan_id", table_name="enrichment_run")
    for column in reversed(_RUN_COLUMNS):
        op.drop_column("enrichment_run", column.name)
