"""Where a plan step is running: `enrichment_run.process` (host, worker pid, step pid, log file).

Written by `cipher worker` when it starts a step, so an admin can find the process and its log
on that host (`cipher runs`, the pipeline's step details). Cleared when the step is re-queued.

Revision ID: 0056_run_process
Revises: 0055_run_plans
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0056_run_process"
down_revision: str | None = "0055_run_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column."""
    op.add_column("enrichment_run", sa.Column("process", JSONB(), nullable=True))


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("enrichment_run", "process")
