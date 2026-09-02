from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas._base.common import Sex
from cipher.schemas.identity.person import PersonSource

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.entity import EntityTable
    from cipher.datastores.postgres.tables.face import FaceTable
    from cipher.datastores.postgres.tables.face_match import FaceMatchTable


class PersonTable(Base):
    """Person table model for Postgres.

    Represents a real-world individual of interest, independent of any
    system user/analyst account. Faces (and, later, other evidence types)
    reference a person; a person does not reference a user. There is no
    centroid embedding here — matching is done against a person's
    representative faces (see `FaceTable.is_representative`).
    """

    __tablename__ = "person"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sex: Mapped[Sex | None] = mapped_column(Enum(Sex, native_enum=False), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    source: Mapped[PersonSource] = mapped_column(
        Enum(PersonSource, native_enum=False), nullable=False, default=PersonSource.MANUAL
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

    faces: Mapped[list["FaceTable"]] = relationship(back_populates="person", lazy="select")
    face_matches: Mapped[list["FaceMatchTable"]] = relationship(
        back_populates="person", cascade="all, delete-orphan", lazy="select"
    )
    # Bridge to the knowledge-graph node. The FK lives on `entity.person_id`, so
    # this adds no column to `person` -- only the reverse accessor.
    entity: Mapped["EntityTable | None"] = relationship(
        back_populates="person", uselist=False, lazy="select"
    )

    __table_args__ = (Index("ix_person_tags_gin", "tags", postgresql_using="gin"),)
