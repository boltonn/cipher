from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.comment import CommentableType

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.user import UserTable


class CommentTable(Base):
    """Comment table model for Postgres."""

    __tablename__ = "comment"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    content: Mapped[str] = mapped_column(String(5000), nullable=False)

    commentable_type: Mapped[CommentableType] = mapped_column(
        Enum(CommentableType, native_enum=False), nullable=False, index=True
    )
    commentable_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    user: Mapped["UserTable"] = relationship(lazy="select")
