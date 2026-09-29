ALTER TABLE face ADD COLUMN IF NOT EXISTS date_rejected timestamptz;
ALTER TABLE face ADD COLUMN IF NOT EXISTS rejection_method varchar(9);
ALTER TABLE face ADD COLUMN IF NOT EXISTS rejection_confidence double precision;
CREATE INDEX IF NOT EXISTS ix_face_rejected ON face (rejection_method) WHERE date_rejected IS NOT NULL;
ALTER TABLE face DROP CONSTRAINT IF EXISTS ck_face_rejected_unassigned;
ALTER TABLE face ADD CONSTRAINT ck_face_rejected_unassigned CHECK (date_rejected IS NULL OR person_id IS NULL);
