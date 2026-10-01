"""Flag texts whose mentions an analyst corrected: `extracted_text.is_mentions_corrected` + who.

Set whenever an analyst draws, relabels (span / type), or deletes a mention in
the text view -- so the text and its current mentions can be picked out as
retraining material. Backfilled from existing analyst-drawn mentions.

Also stamps `face.embedding_model` on existing rows (detection and embedding come
from the same insightface pack; it was never recorded).

Revision ID: 0028_text_mentions_corrected
Revises: 0027_chunk_date_content
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_text_mentions_corrected"
down_revision: str | None = "0027_chunk_date_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "extracted_text",
        sa.Column("is_mentions_corrected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "extracted_text",
        sa.Column("mentions_reviewed_by", sa.String(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    )
    op.execute(
        "UPDATE extracted_text SET is_mentions_corrected = true WHERE id IN "
        "(SELECT mentioned_id FROM mention WHERE extractor = 'manual' AND mentioned_type = 'EXTRACTED_TEXT')"
    )
    op.execute(
        "UPDATE face SET embedding_model = detector_model "
        "WHERE embedding_model IS NULL AND embedding IS NOT NULL AND detector_model = 'insightface-buffalo_l'"
    )


def downgrade() -> None:
    op.drop_column("extracted_text", "mentions_reviewed_by")
    op.drop_column("extracted_text", "is_mentions_corrected")
