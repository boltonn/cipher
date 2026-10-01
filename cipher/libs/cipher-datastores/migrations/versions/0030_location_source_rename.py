"""Name the two text-derived `location.source` values after the attribute that was mentioned.

`NAMED_MENTION` -> `NAME_MENTION` (a place name in text, located by the
gazetteer) and `TEXT_MENTION` -> `COORDINATE_MENTION` (a lat/long written in
text), mirroring `mention.entity_attribute` (`name` / `coordinate`). The column
is a non-native Enum storing the member name, so it is widened to fit and the
partial unique index is rebuilt on the new name.

Revision ID: 0030_location_source_rename
Revises: 0029_face_match_outlives_person
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_location_source_rename"
down_revision: str | None = "0029_face_match_outlives_person"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename(*, name: tuple[str, str], coordinate: tuple[str, str], length: int) -> None:
    op.drop_index("uq_location_file_source", table_name="location")
    if length > 13:
        op.alter_column("location", "source", type_=sa.String(length))
    for old, new in (name, coordinate):
        op.execute(f"UPDATE location SET source = '{new}' WHERE source = '{old}'")
    if length <= 13:
        op.alter_column("location", "source", type_=sa.String(length))
    op.execute(
        "CREATE UNIQUE INDEX uq_location_file_source ON location (file_id, source) "
        f"WHERE source <> '{coordinate[1]}'"
    )


def upgrade() -> None:
    _rename(name=("NAMED_MENTION", "NAME_MENTION"), coordinate=("TEXT_MENTION", "COORDINATE_MENTION"), length=18)


def downgrade() -> None:
    _rename(name=("NAME_MENTION", "NAMED_MENTION"), coordinate=("COORDINATE_MENTION", "TEXT_MENTION"), length=13)
