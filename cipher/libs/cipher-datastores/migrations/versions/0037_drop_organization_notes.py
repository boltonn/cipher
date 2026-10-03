"""Drop `organization.notes`: comments on the entity cover analyst notes.

Revision ID: 0037_drop_organization_notes
Revises: 0036_tag
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_drop_organization_notes"
down_revision: str | None = "0036_tag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the column."""
    op.drop_column("organization", "notes")


def downgrade() -> None:
    """Restore the column."""
    op.add_column("organization", sa.Column("notes", sa.String(), nullable=True))
