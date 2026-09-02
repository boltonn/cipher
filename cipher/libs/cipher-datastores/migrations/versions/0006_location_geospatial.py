"""Make `location` a standalone geospatial table + wire EXIF photo coordinates.

- `location` is no longer 1:1-bound to `entity` via `entity_id`. It becomes a
  standalone point table (mirroring shadowbot's `location`): PostGIS `geom`
  (NOT NULL -- an address with no fix stays an unresolved mention), optional
  `file_id` / `dataset_id`, and `name` / `category` / `address` / `city` /
  `admin_area` / `country` / `tags` / `attributes` / `altitude` / `source_id` /
  `date_recorded`. `address_text` -> `address`. `(file_id, source)` is unique
  for idempotent extractor upserts.
- A location that *is* a knowledge-graph entity is bridged by shared id, like
  `person`: new `entity.location_id` (unique FK), and `create_entity` sets
  `location.id == entity.id`.
- `image` gains `gps_latitude` / `gps_longitude` (already extracted from EXIF,
  previously discarded).

Revision ID: 0006_location_geospatial
Revises: 0005_relationship_dataset_nullable
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_location_geospatial"
down_revision: str | None = "0005_relationship_dataset_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # --- location: drop the entity_id bridge, become standalone + geospatial ---
    op.drop_column("location", "entity_id")
    op.alter_column("location", "address_text", new_column_name="address")
    op.alter_column("location", "latitude", existing_type=sa.Float(), nullable=False)
    op.alter_column("location", "longitude", existing_type=sa.Float(), nullable=False)

    op.add_column("location", sa.Column("file_id", sa.String(), nullable=True))
    op.add_column("location", sa.Column("dataset_id", sa.String(), nullable=True))
    op.add_column(
        "location",
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
            nullable=False,
        ),
    )
    op.add_column("location", sa.Column("altitude", sa.Float(), nullable=True))
    op.add_column("location", sa.Column("bearing", sa.Integer(), nullable=True))
    op.add_column("location", sa.Column("pitch", sa.Float(), nullable=True))
    op.add_column("location", sa.Column("velocity", sa.Float(), nullable=True))
    op.add_column("location", sa.Column("velocity_accuracy", sa.Float(), nullable=True))
    op.add_column("location", sa.Column("horizontal_accuracy", sa.Float(), nullable=True))
    op.add_column("location", sa.Column("vertical_accuracy", sa.Float(), nullable=True))
    op.add_column("location", sa.Column("name", sa.String(), nullable=True))
    op.add_column("location", sa.Column("category", sa.String(), nullable=True))
    op.add_column("location", sa.Column("city", sa.String(), nullable=True))
    op.add_column("location", sa.Column("source_id", sa.String(), nullable=True))
    op.add_column("location", sa.Column("date_recorded", sa.DateTime(timezone=True), nullable=True))
    op.add_column("location", sa.Column("tags", postgresql.JSONB(), server_default="[]", nullable=False))
    op.add_column("location", sa.Column("attributes", postgresql.JSONB(), server_default="{}", nullable=False))

    op.create_foreign_key("fk_location_file_id", "location", "file", ["file_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_location_dataset_id", "location", "dataset", ["dataset_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_location_file_source", "location", ["file_id", "source"])

    op.create_index("ix_location_file_id", "location", ["file_id"])
    op.create_index("ix_location_dataset_id", "location", ["dataset_id"])
    op.create_index("ix_location_name", "location", ["name"])
    op.create_index("ix_location_category", "location", ["category"])
    op.create_index("ix_location_source", "location", ["source"])
    op.create_index("ix_location_date_recorded", "location", ["date_recorded"])
    op.create_index("ix_location_source_source_id", "location", ["source", "source_id"])
    op.create_index("ix_location_geom", "location", ["geom"], postgresql_using="gist")

    # --- entity: shared-id bridge to location (mirrors person_id) ---
    op.add_column("entity", sa.Column("location_id", sa.String(), nullable=True))
    op.create_unique_constraint("uq_entity_location_id", "entity", ["location_id"])
    op.create_foreign_key("fk_entity_location_id", "entity", "location", ["location_id"], ["id"], ondelete="SET NULL")

    # --- image: keep the EXIF coordinate instead of discarding it ---
    op.add_column("image", sa.Column("gps_latitude", sa.Float(), nullable=True))
    op.add_column("image", sa.Column("gps_longitude", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("image", "gps_longitude")
    op.drop_column("image", "gps_latitude")

    op.drop_constraint("fk_entity_location_id", "entity", type_="foreignkey")
    op.drop_constraint("uq_entity_location_id", "entity", type_="unique")
    op.drop_column("entity", "location_id")

    for name in (
        "ix_location_geom",
        "ix_location_source_source_id",
        "ix_location_date_recorded",
        "ix_location_source",
        "ix_location_category",
        "ix_location_name",
        "ix_location_dataset_id",
        "ix_location_file_id",
    ):
        op.drop_index(name, table_name="location")
    op.drop_constraint("uq_location_file_source", "location", type_="unique")
    op.drop_constraint("fk_location_dataset_id", "location", type_="foreignkey")
    op.drop_constraint("fk_location_file_id", "location", type_="foreignkey")

    for col in (
        "attributes",
        "tags",
        "date_recorded",
        "source_id",
        "city",
        "category",
        "name",
        "vertical_accuracy",
        "horizontal_accuracy",
        "velocity_accuracy",
        "velocity",
        "pitch",
        "bearing",
        "altitude",
        "geom",
        "dataset_id",
        "file_id",
    ):
        op.drop_column("location", col)

    op.alter_column("location", "address", new_column_name="address_text")
    op.add_column("location", sa.Column("entity_id", sa.String(), nullable=False))
    op.create_unique_constraint("uq_location_entity_id", "location", ["entity_id"])
    op.create_index("ix_location_entity_id", "location", ["entity_id"])
    op.create_foreign_key("fk_location_entity_id", "location", "entity", ["entity_id"], ["id"], ondelete="CASCADE")
