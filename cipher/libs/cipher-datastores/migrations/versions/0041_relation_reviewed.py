"""`mention_relationship.date_reviewed`: an analyst accepted or dismissed it as a name-level suggestion.

Revision ID: 0041_relation_reviewed
Revises: 0040_file_source_tags
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_relation_reviewed"
down_revision: str | None = "0040_file_source_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column."""
    op.add_column("mention_relationship", sa.Column("date_reviewed", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("mention_relationship", "date_reviewed")
