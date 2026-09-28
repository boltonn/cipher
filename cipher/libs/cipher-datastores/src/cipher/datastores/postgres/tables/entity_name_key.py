from sqlalchemy import ForeignKey, Index, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base


class EntityNameKeyTable(Base):
    """A materialized blocking index over `cipher.names.entity_keys`.

    One row per `(entity, key_type, key)`: the transliterated / phonetic /
    sorted-token / surname / given+surname forms of a person / organization /
    location entity's display name and aliases. Entity resolution equality-joins
    an unresolved mention's keys against this table to generate candidates.

    Purely derived state, safe to drop and rebuild: kept in lockstep by an inline
    refresh on every entity write, `ON DELETE CASCADE` from `entity`, and the
    `backfill-entity-name-keys` sweep. Selector entities are not keyed (they
    resolve by exact value, not name).
    """

    __tablename__ = "entity_name_key"

    entity_id: Mapped[str] = mapped_column(String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False)
    key_type: Mapped[str] = mapped_column(String(16), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("entity_id", "key_type", "key", name="pk_entity_name_key"),
        # The candidate probe: equality on (key_type, key). INCLUDE entity_id so the
        # lookup is index-only.
        Index(
            "ix_entity_name_key_lookup",
            "key_type",
            "key",
            postgresql_include=["entity_id"],
        ),
    )
