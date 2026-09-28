-- Dev-DB apply for migrations 0021 + 0022 (local Postgres is unstamped; built
-- via create_all, so alembic upgrade can't run). Idempotent.

-- 0021: staging milestone
ALTER TABLE dataset ADD COLUMN IF NOT EXISTS date_staged timestamptz;

-- 0022: enrichment_run audit + calibration log
CREATE TABLE IF NOT EXISTS enrichment_run (
    id                 varchar PRIMARY KEY,
    enrichment_type    varchar NOT NULL,
    dataset_id         varchar REFERENCES dataset(id) ON DELETE SET NULL,
    device             varchar NOT NULL DEFAULT 'na',
    unit               varchar NOT NULL DEFAULT 'file',
    unit_count         integer NOT NULL DEFAULT 0,
    params             jsonb   NOT NULL DEFAULT '{}'::jsonb,
    status             varchar NOT NULL DEFAULT 'running',
    error_message      text,
    date_started       timestamptz NOT NULL DEFAULT now(),
    date_completed     timestamptz,
    duration_seconds   double precision
);
CREATE INDEX IF NOT EXISTS ix_enrichment_run_enrichment_type ON enrichment_run (enrichment_type);
CREATE INDEX IF NOT EXISTS ix_enrichment_run_dataset_id ON enrichment_run (dataset_id);
CREATE INDEX IF NOT EXISTS ix_enrichment_run_type_device_status ON enrichment_run (enrichment_type, device, status);
