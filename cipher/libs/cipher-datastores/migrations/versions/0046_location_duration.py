"""`location.duration_seconds`: how long an observation lasted (a call at a tower, a stay).

Tabular location points are now one per dated row (`date_recorded` = the row's time)
rather than one per distinct coordinate, so a call log becomes a timeline.

Revision ID: 0046_location_duration
Revises: 0045_file_summary
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_location_duration"
down_revision: str | None = "0045_file_summary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the duration column."""
    op.add_column("location", sa.Column("duration_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    """Drop the duration column."""
    op.drop_column("location", "duration_seconds")
