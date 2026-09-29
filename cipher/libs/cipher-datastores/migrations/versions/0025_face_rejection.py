"""Let a face be marked 'not a face' (detector false positive, e.g. a pet).

`date_rejected` set = rejected; `rejection_method` says whether an analyst did it
(manual, the negative exemplars) or it was auto-rejected by similarity to one
(automatic, with `rejection_confidence` = that similarity). A rejected face is
never assigned. Purely additive.

Revision ID: 0025_face_rejection
Revises: 0024_entity_match_merge_group
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_face_rejection"
down_revision: str | None = "0024_entity_match_merge_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("face", sa.Column("date_rejected", sa.DateTime(timezone=True), nullable=True))
    op.add_column("face", sa.Column("rejection_method", sa.String(length=9), nullable=True))
    op.add_column("face", sa.Column("rejection_confidence", sa.Float(), nullable=True))
    op.create_index(
        "ix_face_rejected",
        "face",
        ["rejection_method"],
        postgresql_where=sa.text("date_rejected IS NOT NULL"),
    )
    op.create_check_constraint("ck_face_rejected_unassigned", "face", "date_rejected IS NULL OR person_id IS NULL")


def downgrade() -> None:
    op.drop_constraint("ck_face_rejected_unassigned", "face", type_="check")
    op.drop_index("ix_face_rejected", table_name="face")
    op.drop_column("face", "rejection_confidence")
    op.drop_column("face", "rejection_method")
    op.drop_column("face", "date_rejected")
