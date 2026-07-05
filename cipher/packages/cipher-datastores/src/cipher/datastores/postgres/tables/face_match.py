from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.face_match import FaceMatchMethod, FaceMatchStatus

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.face import FaceTable
    from cipher.datastores.postgres.tables.person import PersonTable
    from cipher.datastores.postgres.tables.user import UserTable


class FaceMatchTable(Base):
    """Candidate face-to-person match awaiting (or having received) review."""

    __tablename__ = "face_match"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    face_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("face.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("person.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_method: Mapped[FaceMatchMethod] = mapped_column(
        Enum(FaceMatchMethod, native_enum=False),
        nullable=False,
        default=FaceMatchMethod.AUTOMATIC_SIMILARITY,
    )
    status: Mapped[FaceMatchStatus] = mapped_column(
        Enum(FaceMatchStatus, native_enum=False),
        nullable=False,
        default=FaceMatchStatus.PENDING,
        index=True,
    )

    reviewed_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String, nullable=True)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    face: Mapped["FaceTable"] = relationship(back_populates="match_candidates", lazy="select")
    person: Mapped["PersonTable"] = relationship(back_populates="face_matches", lazy="select")
    reviewer: Mapped["UserTable | None"] = relationship(lazy="select")

    __table_args__ = (
        UniqueConstraint("face_id", "person_id", name="uq_face_match_face_person"),
        Index(
            "idx_face_match_pending",
            "person_id",
            "status",
            postgresql_where=text("status = 'pending'"),
        ),
    )
