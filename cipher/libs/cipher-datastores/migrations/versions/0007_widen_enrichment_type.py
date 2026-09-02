"""Widen enrichment.enrichment_type to fit RELATIONSHIP_EXTRACTION.

`enrichment_type` is `Enum(EnrichmentType, native_enum=False)`, which SQLAlchemy
renders as a VARCHAR sized to the longest member. Databases created before the
`relationship_extraction` member existed have VARCHAR(19), which truncates the
23-char `RELATIONSHIP_EXTRACTION` on insert. Fresh `create_all` DBs are already
VARCHAR(23); this brings existing DBs in line.

Revision ID: 0007_widen_enrichment_type
Revises: 0006_location_geospatial
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_widen_enrichment_type"
down_revision: str | None = "0006_location_geospatial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "enrichment",
        "enrichment_type",
        existing_type=sa.String(length=19),
        type_=sa.String(length=23),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute("DELETE FROM enrichment WHERE char_length(enrichment_type) > 19")
    op.alter_column(
        "enrichment",
        "enrichment_type",
        existing_type=sa.String(length=23),
        type_=sa.String(length=19),
        existing_nullable=False,
    )
