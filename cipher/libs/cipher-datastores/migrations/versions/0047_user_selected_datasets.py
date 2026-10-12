"""`user.selected_dataset_ids`: the datasets a user is working in, kept server-side.

Replaces per-page browser storage, which kept ids of deleted datasets (and of every dataset
after a database rebuild). Dataset deletes remove the id from every selection.

Revision ID: 0047_user_selected_datasets
Revises: 0046_location_duration
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_user_selected_datasets"
down_revision: str | None = "0046_location_duration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the selection column."""
    op.add_column(
        "user",
        sa.Column("selected_dataset_ids", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    """Drop the selection column."""
    op.drop_column("user", "selected_dataset_ids")
