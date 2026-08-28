from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.message import TEXT_EMBEDDING_DIMENSION
from cipher.schemas.ontology import EntitySource, EntityType

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.person import PersonTable

ENTITY_NAME_EMBEDDING_DIMENSION = TEXT_EMBEDDING_DIMENSION


class EntityTable(Base):
    """The thin supertype node of the knowledge graph.

    Type-specific detail lives in a 1:1 row in `organization` / `location` /
    `selector` / the legacy `person` table, reached via `entity_id`. Mentions
    and relationships reference `entity.id`.
    """

    __tablename__ = "entity"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    dataset_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=True, index=True
    )
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType, native_enum=False), nullable=False)

    display_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    display_name_normalized: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    source: Mapped[EntitySource] = mapped_column(
        Enum(EntitySource, native_enum=False), nullable=False, default=EntitySource.EXTRACTION
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    name_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(ENTITY_NAME_EMBEDDING_DIMENSION), nullable=True
    )

    person_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("person.id", ondelete="SET NULL"), nullable=True, unique=True
    )

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    person: Mapped["PersonTable | None"] = relationship(back_populates="entity", lazy="select")

    __table_args__ = (
        Index(
            "ix_entity_name_trgm",
            "display_name_normalized",
            postgresql_using="gin",
            postgresql_ops={"display_name_normalized": "gin_trgm_ops"},
        ),
        Index(
            "hnsw_index_entity_name_embedding",
            "name_embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"name_embedding": "vector_cosine_ops"},
        ),
        Index("ix_entity_dataset_type", "dataset_id", "entity_type"),
        Index("ix_entity_tags_gin", "tags", postgresql_using="gin"),
    )
