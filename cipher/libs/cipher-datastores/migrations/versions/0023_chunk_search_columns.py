"""Add `chunk.embedding` + `chunk.text_tsv` and their indexes.

The Postgres retrieval backend's search columns (docs/retrieval-architecture.md,
P1b): a 1024-d vector for semantic search (HNSW, cosine) and a per-language
`tsvector` for the `core` keyword ranker (GIN). Both nullable and populated by
the embed pipeline. The ranker-specific keyword index on `chunk.text` (BM25 for
`pg_search`, GIN for `pg_bigm`/`pgroonga`) is created at runtime by
`PostgresChunkRetrievalRepository` -- it depends on an optional extension and is
not portable into a migration.

Revision ID: 0023_chunk_search_columns
Revises: 0022_enrichment_run
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0023_chunk_search_columns"
down_revision: str | None = "0022_enrichment_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIM = 1024


def upgrade() -> None:
    op.add_column("chunk", sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=True))
    op.add_column("chunk", sa.Column("text_tsv", postgresql.TSVECTOR(), nullable=True))
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "chunk",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_chunk_text_tsv", "chunk", ["text_tsv"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_chunk_text_tsv", table_name="chunk")
    op.drop_index("ix_chunk_embedding_hnsw", table_name="chunk")
    op.drop_column("chunk", "text_tsv")
    op.drop_column("chunk", "embedding")
