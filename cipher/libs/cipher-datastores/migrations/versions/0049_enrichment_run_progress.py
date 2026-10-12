"""`enrichment_run.progress`: live per-step progress for a run with several steps.

A dataset-wide sweep like entity resolution has no per-file queue to count, so it reports
its own steps -- `{"steps": [{"name", "label", "done", "total", "status"}]}` -- while running.

Revision ID: 0049_enrichment_run_progress
Revises: 0048_mention_relationship_review
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0049_enrichment_run_progress"
down_revision: str | None = "0048_mention_relationship_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the progress column."""
    op.add_column("enrichment_run", sa.Column("progress", JSONB(), nullable=True))


def downgrade() -> None:
    """Drop the progress column."""
    op.drop_column("enrichment_run", "progress")
