from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base

# CLIR multilingual text embedding (Jina). Kept local to the table like
# IMAGE_EMBEDDING_DIMENSION; must match the model the embed pipeline uses.
CHUNK_EMBEDDING_DIMENSION = 1024


class ChunkTable(Base):
    """One embedded slice of a file's extracted text -- the retrieval unit.

    Identity + span + the searchable copy (`text`, `embedding`, and, only for the
    `core` keyword ranker, `text_tsv`). Every `mention` joins here via
    `mention.chunk_id`, and the embed pipeline diffs against this row on
    re-extraction so that join survives a re-embed. `id` is deterministic --
    `cipher.schemas.content.search.chunk_id_for` -- so a re-embed upserts and
    content-identical files in a dataset share one row.

    The ranker-specific keyword index on `text` (BM25 for `pg_search`, GIN for
    `pg_bigm`/`pgroonga`) is created by `PostgresChunkRetrievalRepository`
    according to `RETRIEVAL__TEXT_RANKER`, not here -- it depends on an optional
    extension. `text_tsv` + its GIN are always created (core Postgres) and simply
    stay empty when a non-`core` ranker is active.
    """

    __tablename__ = "chunk"

    id: Mapped[str] = mapped_column(String, primary_key=True)

    dataset_id: Mapped[str] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(
        String, ForeignKey("file.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sha256: Mapped[str] = mapped_column(String, nullable=False, index=True)
    filetype_group: Mapped[str] = mapped_column(String, nullable=False)

    # Files in this dataset with identical content (same sha256) that share this
    # chunk record instead of storing their own copy. Always includes `file_id`.
    # Mirrors the retrieval store's own dedup; a mention in any of these files
    # resolves to this row (the chunk<->mention join is content-keyed).
    duplicate_file_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Best-effort; from a detector if one runs. NOT required for search -- the
    # default pg_search ICU tokenizer is script-agnostic. Feeds result filtering,
    # the optional per-language stemmer, and display.
    language: Mapped[str | None] = mapped_column(String, nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(CHUNK_EMBEDDING_DIMENSION), nullable=True)
    # Per-language `tsvector`, writer-populated. Only used by the `core` keyword
    # ranker; NULL under pg_search / pgroonga / pg_bigm.
    text_tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_chunk_file_offset", "file_id", "start_offset"),
        Index("ix_chunk_dataset_group", "dataset_id", "filetype_group"),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunk_text_tsv", "text_tsv", postgresql_using="gin"),
    )
