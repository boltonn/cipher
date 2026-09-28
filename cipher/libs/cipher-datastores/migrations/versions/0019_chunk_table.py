"""Add the `chunk` table and `mention.chunk_id`.

The stable identity + span anchor for embedded text slices, and the materialized
`chunk <-> mention` range-join (docs/retrieval-architecture.md, P0). `chunk.id`
equals the retrieval store's document id (see
`cipher.schemas.content.search.chunk_id_for`). `mention.chunk_id` is nullable and
its indexes partial until a later step populates it at extraction time. Purely
additive -- nothing reads either yet.

Revision ID: 0019_chunk_table
Revises: 0018_entity_match_name_group
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_chunk_table"
down_revision: str | None = "0018_entity_match_name_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(), sa.ForeignKey("file.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("filetype_group", sa.String(), nullable=False),
        sa.Column(
            "duplicate_file_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column(
            "date_created",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_chunk_dataset_id", "chunk", ["dataset_id"])
    op.create_index("ix_chunk_file_id", "chunk", ["file_id"])
    op.create_index("ix_chunk_sha256", "chunk", ["sha256"])
    op.create_index("ix_chunk_file_offset", "chunk", ["file_id", "start_offset"])
    op.create_index("ix_chunk_dataset_group", "chunk", ["dataset_id", "filetype_group"])

    op.add_column("mention", sa.Column("chunk_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_mention_chunk_id", "mention", "chunk", ["chunk_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(
        "ix_mention_chunk", "mention", ["chunk_id"], postgresql_where=sa.text("chunk_id IS NOT NULL")
    )
    op.create_index(
        "ix_mention_chunk_entity",
        "mention",
        ["chunk_id", "entity_id"],
        postgresql_where=sa.text("chunk_id IS NOT NULL"),
    )
    op.create_index(
        "ix_mention_chunk_selector",
        "mention",
        ["chunk_id", "selector_type"],
        postgresql_where=sa.text("chunk_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_mention_chunk_selector", table_name="mention")
    op.drop_index("ix_mention_chunk_entity", table_name="mention")
    op.drop_index("ix_mention_chunk", table_name="mention")
    op.drop_constraint("fk_mention_chunk_id", "mention", type_="foreignkey")
    op.drop_column("mention", "chunk_id")

    op.drop_index("ix_chunk_dataset_group", table_name="chunk")
    op.drop_index("ix_chunk_file_offset", table_name="chunk")
    op.drop_index("ix_chunk_sha256", table_name="chunk")
    op.drop_index("ix_chunk_file_id", table_name="chunk")
    op.drop_index("ix_chunk_dataset_id", table_name="chunk")
    op.drop_table("chunk")
