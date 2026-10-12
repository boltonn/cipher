"""`chunk.is_summary` + `chunk.generated_by`: AI file summaries stored as chunks.

A summary is one extra chunk per (dataset, content hash) -- `is_summary`, `chunk_index = -1`,
`generated_by` = the model -- so it is searchable like any chunk and shared by
content-identical files. The flag also fits other generated whole-file descriptions (image
captions). Everything that reads chunks as a file's text (spans, mentions, text
reconstruction) filters `NOT is_summary`.

Revision ID: 0045_file_summary
Revises: 0044_table_filetype_group
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_file_summary"
down_revision: str | None = "0044_table_filetype_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the summary flag + generator columns."""
    op.add_column("chunk", sa.Column("is_summary", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("chunk", sa.Column("generated_by", sa.String(), nullable=True))
    op.create_index(
        "ix_chunk_summary_sha256", "chunk", ["sha256"], postgresql_where=sa.text("is_summary"), if_not_exists=True
    )


def downgrade() -> None:
    """Drop summary chunks and the columns."""
    op.execute("DELETE FROM chunk WHERE is_summary")
    op.drop_index("ix_chunk_summary_sha256", table_name="chunk")
    op.drop_column("chunk", "generated_by")
    op.drop_column("chunk", "is_summary")
