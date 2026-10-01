"""Add `chunk.date_content` + index, and index every mention's `normalized_value`.

Search browse ordered chunks by the email `date_sent` / document
`date_content_created` inside `extracted_text.metadata` -- detoasting that JSONB
per chunk (137k rows, ~3.4s on `rag`). The date now lives on the chunk, written
by the embed pipeline and backfilled here. `ix_mention_value` replaces the
selector-only partial index: name groups and the search mention-value filter
key on `normalized_value` for every mention. `ix_chunk_dataset_group_file`
(superseding `ix_chunk_dataset_group`) makes browse's distinct-file total index-only.

Revision ID: 0027_chunk_date_content
Revises: 0026_organization_structure
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_chunk_date_content"
down_revision: str | None = "0026_organization_structure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunk", sa.Column("date_content", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE chunk c SET date_content = "
        "(coalesce(et.metadata->>'date_sent', et.metadata->>'date_content_created'))::timestamp AT TIME ZONE 'UTC' "
        "FROM extracted_text et WHERE et.file_id = c.file_id "
        "AND coalesce(et.metadata->>'date_sent', et.metadata->>'date_content_created') IS NOT NULL"
    )
    op.create_index(
        "ix_chunk_dataset_date_content", "chunk", ["dataset_id", sa.text("date_content DESC NULLS LAST")]
    )
    op.drop_index("ix_chunk_dataset_group", table_name="chunk")
    op.create_index("ix_chunk_dataset_group_file", "chunk", ["dataset_id", "filetype_group", "file_id"])
    op.drop_index("ix_mention_selector_value", table_name="mention")
    op.create_index("ix_mention_value", "mention", ["dataset_id", "normalized_value"])


def downgrade() -> None:
    op.drop_index("ix_mention_value", table_name="mention")
    op.create_index(
        "ix_mention_selector_value",
        "mention",
        ["dataset_id", "normalized_value"],
        postgresql_where=sa.text("selector_type IS NOT NULL"),
    )
    op.drop_index("ix_chunk_dataset_group_file", table_name="chunk")
    op.create_index("ix_chunk_dataset_group", "chunk", ["dataset_id", "filetype_group"])
    op.drop_index("ix_chunk_dataset_date_content", table_name="chunk")
    op.drop_column("chunk", "date_content")
