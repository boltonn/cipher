-- Migration 0023_chunk_search_columns for the unstamped dev DB (create_all, no alembic_version).
-- Additive only; safe to re-run (IF NOT EXISTS).

ALTER TABLE chunk ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE chunk ADD COLUMN IF NOT EXISTS text_tsv tsvector;

CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw
    ON chunk USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS ix_chunk_text_tsv
    ON chunk USING gin (text_tsv);
