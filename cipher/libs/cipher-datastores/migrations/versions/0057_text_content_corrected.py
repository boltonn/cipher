"""Let analysts correct a file's text (OCR mistakes): `extracted_text.is_content_corrected`, who, and where.

`corrected_ranges` are the stretches of `content` a person wrote (`[start, end)`,
zero-width where text was only deleted), carried forward through later
corrections. Extractors re-run after a correction only add mentions there; a
corrected text is never overwritten by a pipeline re-run.

Revision ID: 0057_text_content_corrected
Revises: 0056_run_process
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0057_text_content_corrected"
down_revision: str | None = "0056_run_process"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "extracted_text",
        sa.Column("is_content_corrected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "extracted_text",
        sa.Column("content_corrected_by", sa.String(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("extracted_text", sa.Column("corrected_ranges", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("extracted_text", "corrected_ranges")
    op.drop_column("extracted_text", "content_corrected_by")
    op.drop_column("extracted_text", "is_content_corrected")
