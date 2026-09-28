-- Migration 0020_dataset_staging for the unstamped dev DB (create_all, no alembic_version).
-- `create_all` never ALTERs an existing table, so this column has to be added by hand.
-- Additive only; safe to re-run.

ALTER TABLE dataset ADD COLUMN IF NOT EXISTS date_staged TIMESTAMPTZ;
