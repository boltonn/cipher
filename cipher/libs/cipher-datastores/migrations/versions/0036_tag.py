"""Tag provenance: `tag` records who or what tagged each target, and when.

Targets are `content` (file bytes by sha256 -- images and every copy of a file share
one set of tags), `entity` (any entity type; person and location records mirror their
entity's tags) and `event`. Existing tags are backfilled with source `unknown`:
labels as a user decision, scores as a model's. The `tags` / `negative_tags` /
`tag_scores` columns are then rebuilt from the `tag` rows, which also makes every
copy of the same file carry the same tags.

Revision ID: 0036_tag
Revises: 0035_comment_person_to_entity
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from cipher.datastores.postgres.repositories.tag import PROJECTION_CTE, PROJECTION_UPDATES
from cipher.datastores.postgres.tables.tag import TagTable
from cipher.schemas.interaction.tag import UNKNOWN_TAG_SOURCE, TagTargetType

revision: str = "0036_tag"
down_revision: str | None = "0035_comment_person_to_entity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INSERT = (
    "INSERT INTO tag (id, target_type, target_id, tag, label, score, source_type, source_name, "
    "date_updated) SELECT gen_random_uuid()::text, '{target_type}', target_id, tag, {label}, {score}, "
    "'{source_type}', '" + UNKNOWN_TAG_SOURCE + "', now() FROM ({rows}) r "
    "ON CONFLICT ON CONSTRAINT uq_tag DO NOTHING"
)


def _labels(target_type: str, rows: str, label: str) -> str:
    return _INSERT.format(
        target_type=target_type, label=f"'{label}'", score="NULL", source_type="USER", rows=rows
    )


def _scores(target_type: str, rows: str) -> str:
    return _INSERT.format(target_type=target_type, label="NULL", score="score", source_type="MODEL", rows=rows)


def upgrade() -> None:
    """Create the table, backfill current tags as `unknown`, rebuild the denormalized columns."""
    bind = op.get_bind()
    TagTable.__table__.create(bind, checkfirst=True)

    for column, label in (("tags", "POSITIVE"), ("negative_tags", "NEGATIVE")):
        content = (
            f"SELECT id AS target_id, jsonb_array_elements_text({column}) AS tag FROM image UNION "
            f"SELECT sha256, jsonb_array_elements_text({column}) FROM file"
        )
        op.execute(_labels("CONTENT", content, label))
    op.execute(
        _scores(
            "CONTENT",
            "SELECT target_id, tag, max(score) AS score FROM ("
            "SELECT id AS target_id, key AS tag, value::float AS score FROM image, jsonb_each_text(tag_scores) UNION ALL "
            "SELECT sha256, key, value::float FROM file, jsonb_each_text(tag_scores)) s GROUP BY target_id, tag",
        )
    )
    entity_tags = (
        "SELECT id AS target_id, jsonb_array_elements_text(tags) AS tag FROM entity UNION "
        "SELECT e.id, jsonb_array_elements_text(p.tags) FROM person p JOIN entity e ON e.person_id = p.id UNION "
        "SELECT e.id, jsonb_array_elements_text(l.tags) FROM location l JOIN entity e ON e.location_id = l.id"
    )
    op.execute(_labels("ENTITY", entity_tags, "POSITIVE"))
    op.execute(_labels("EVENT", "SELECT id AS target_id, jsonb_array_elements_text(tags) AS tag FROM event", "POSITIVE"))

    for target_type in TagTargetType:
        ids = [
            row[0]
            for row in bind.execute(
                text("SELECT DISTINCT target_id FROM tag WHERE target_type = :t"), {"t": target_type.name}
            )
        ]
        for statement in PROJECTION_UPDATES[target_type]:
            bind.execute(text(PROJECTION_CTE + statement), {"ids": ids, "target_type": target_type.name})


def downgrade() -> None:
    """Drop the provenance table; the denormalized columns keep their current tags."""
    op.drop_table("tag")
