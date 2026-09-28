-- Migration 0016_event_ical_fields for the unstamped dev DB (create_all, no alembic_version).
-- Additive only; safe to re-run (IF NOT EXISTS).

ALTER TABLE event ADD COLUMN IF NOT EXISTS url VARCHAR;
ALTER TABLE event ADD COLUMN IF NOT EXISTS categories JSONB NOT NULL DEFAULT '[]';
ALTER TABLE event ADD COLUMN IF NOT EXISTS sensitivity VARCHAR(32);
ALTER TABLE event ADD COLUMN IF NOT EXISTS uid VARCHAR;
ALTER TABLE event ADD COLUMN IF NOT EXISTS recurrence_rule VARCHAR;
ALTER TABLE event ADD COLUMN IF NOT EXISTS sequence INTEGER;
ALTER TABLE event ADD COLUMN IF NOT EXISTS source_created TIMESTAMPTZ;
ALTER TABLE event ADD COLUMN IF NOT EXISTS source_last_modified TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_event_uid ON event (uid);

ALTER TABLE event_participant ADD COLUMN IF NOT EXISTS raw_email VARCHAR;
ALTER TABLE event_participant ADD COLUMN IF NOT EXISTS rsvp_status VARCHAR(32);
ALTER TABLE event_participant ADD COLUMN IF NOT EXISTS is_resource BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS ix_event_participant_raw_email ON event_participant (raw_email);
