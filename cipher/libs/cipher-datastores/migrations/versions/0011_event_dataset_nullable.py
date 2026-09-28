"""Make `event.dataset_id` nullable.

An event is a dated real-world occurrence, not an artefact of one ingest -- like
`location`, it can be analyst-authored or span datasets. `file_id` remains the
provenance link; `dataset_id` is now an optional scoping filter.

Revision ID: 0011_event_dataset_nullable
Revises: 0010_mention_relationship
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_event_dataset_nullable"
down_revision: str | None = "0010_mention_relationship"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("event", "dataset_id", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM event WHERE dataset_id IS NULL")
    op.alter_column("event", "dataset_id", existing_type=sa.String(), nullable=False)
