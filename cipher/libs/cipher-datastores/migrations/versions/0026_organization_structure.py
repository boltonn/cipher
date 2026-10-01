"""Organization hierarchy + category.

`org_type` (never populated) becomes `category`, the same free-text style as
`location.category`. `parent_id` points at the organization this one is a unit of
(division, office, branch); it's mirrored as the org's single `part_of` edge.

Revision ID: 0026_organization_structure
Revises: 0025_face_rejection
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_organization_structure"
down_revision: str | None = "0025_face_rejection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("organization", "org_type", new_column_name="category")
    op.create_index("ix_organization_category", "organization", ["category"])
    op.add_column(
        "organization",
        sa.Column("parent_id", sa.String(), sa.ForeignKey("entity.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_organization_parent_id", "organization", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_organization_parent_id", table_name="organization")
    op.drop_column("organization", "parent_id")
    op.drop_index("ix_organization_category", table_name="organization")
    op.alter_column("organization", "category", new_column_name="org_type")
