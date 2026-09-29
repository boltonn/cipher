-- Remove duplicate email_headers mentions (one row kept per email / header field / value / attribute).
-- Keeps the copy referenced by entity_match / mention_relationship / relationship candidates first,
-- then a resolved copy, then the oldest. Run: psql -h 0.0.0.0 -U cipher -d cipher -f scratchpad/dedupe_header_mentions.sql
BEGIN;
CREATE TEMP TABLE dup_mention ON COMMIT DROP AS
SELECT id FROM (
  SELECT m.id, row_number() OVER (
    PARTITION BY m.dataset_id, m.mentioned_id, m.field_path, m.normalized_value, coalesce(m.entity_attribute, ''), m.extractor
    ORDER BY (EXISTS (SELECT 1 FROM entity_match x WHERE x.mention_id = m.id)
           OR EXISTS (SELECT 1 FROM mention_relationship r WHERE r.src_mention_id = m.id OR r.dst_mention_id = m.id)
           OR EXISTS (SELECT 1 FROM entity_relationship_candidate c WHERE c.evidence_mention_id = m.id)) DESC,
             (m.entity_id IS NOT NULL) DESC, m.date_created, m.id) AS rn
  FROM mention m WHERE m.extractor = 'email_headers'
) t WHERE rn > 1;
SELECT count(*) AS to_delete FROM dup_mention;
DELETE FROM mention WHERE id IN (SELECT id FROM dup_mention);
COMMIT;
