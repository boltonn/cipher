"""`mention_relationship.is_accepted` + `reviewed_by`: who settled an extracted relationship, and how.

`date_reviewed` alone could not tell an accepted relationship from a rejected one, so the
email-signature review could not show either. Null while pending (and for rows reviewed
before this column existed).

Revision ID: 0048_mention_relationship_review
Revises: 0047_user_selected_datasets
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_mention_relationship_review"
down_revision: str | None = "0047_user_selected_datasets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the review columns."""
    op.add_column("mention_relationship", sa.Column("is_accepted", sa.Boolean(), nullable=True))
    op.add_column("mention_relationship", sa.Column("reviewed_by", sa.String(), nullable=True))


def downgrade() -> None:
    """Drop the review columns."""
    op.drop_column("mention_relationship", "reviewed_by")
    op.drop_column("mention_relationship", "is_accepted")
