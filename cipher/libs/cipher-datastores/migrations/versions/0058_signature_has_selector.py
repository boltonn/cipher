"""Offer the email signature's phones, emails and websites as `has_selector` relations to review.

`extract-signatures` now records signer -> phone / email and company -> website as
mention relations (before, only `resolve-entities` linked them by `field_path`, so
the email-signature review never showed them). This adds them for signatures
already read: same text, the selector in the signer's or the company's field.

Revision ID: 0058_signature_has_selector
Revises: 0057_text_content_corrected
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0058_signature_has_selector"
down_revision: str | None = "0057_text_content_corrected"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO mention_relationship (
            id, dataset_id, src_mention_id, dst_mention_id, relationship_type, directed,
            confidence, file_id, context, attributes, extractor, date_created
        )
        SELECT gen_random_uuid()::text, owner.dataset_id, owner.id, sel.id, 'HAS_SELECTOR', true,
               coalesce(owner.extraction_confidence, 1.0), owner.file_id, owner.context, '{}'::jsonb,
               'signature', now()
        FROM mention owner
        JOIN mention sel
          ON sel.mentioned_id = owner.mentioned_id
         AND sel.field_path = owner.field_path
         AND sel.extractor = 'signature'
         AND sel.entity_type = 'SELECTOR'
         AND sel.start_offset IS NOT NULL
        WHERE owner.extractor = 'signature'
          AND owner.entity_attribute = 'name'
          AND owner.selector_type IS NULL
          AND owner.field_path IN ('signature.person', 'signature.unit.0')
        ON CONFLICT ON CONSTRAINT uq_mention_relationship_triple DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM mention_relationship "
        "WHERE extractor = 'signature' AND relationship_type = 'HAS_SELECTOR' AND date_reviewed IS NULL"
    )
