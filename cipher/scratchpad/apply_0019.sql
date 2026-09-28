-- Migration 0019_chunk_table for the unstamped dev DB (create_all, no alembic_version).
-- Additive only; safe to re-run (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS chunk (
    id             VARCHAR PRIMARY KEY,
    dataset_id     VARCHAR NOT NULL REFERENCES dataset (id) ON DELETE CASCADE,
    file_id        VARCHAR NOT NULL REFERENCES file (id) ON DELETE CASCADE,
    sha256         VARCHAR NOT NULL,
    filetype_group VARCHAR NOT NULL,
    duplicate_file_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    chunk_index    INTEGER NOT NULL,
    start_offset   INTEGER NOT NULL,
    end_offset     INTEGER NOT NULL,
    text           TEXT NOT NULL,
    language       VARCHAR,
    date_created   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chunk_dataset_id ON chunk (dataset_id);
CREATE INDEX IF NOT EXISTS ix_chunk_file_id ON chunk (file_id);
CREATE INDEX IF NOT EXISTS ix_chunk_sha256 ON chunk (sha256);
CREATE INDEX IF NOT EXISTS ix_chunk_file_offset ON chunk (file_id, start_offset);
CREATE INDEX IF NOT EXISTS ix_chunk_dataset_group ON chunk (dataset_id, filetype_group);

ALTER TABLE mention ADD COLUMN IF NOT EXISTS chunk_id VARCHAR;
DO $$ BEGIN
    ALTER TABLE mention ADD CONSTRAINT fk_mention_chunk_id
        FOREIGN KEY (chunk_id) REFERENCES chunk (id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS ix_mention_chunk ON mention (chunk_id) WHERE chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_mention_chunk_entity ON mention (chunk_id, entity_id) WHERE chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_mention_chunk_selector ON mention (chunk_id, selector_type) WHERE chunk_id IS NOT NULL;
