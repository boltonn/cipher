from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Self, TypedDict

from pydantic import Field
from uuid_utils import uuid4

from cipher.schemas.base import BaseModel
from cipher.schemas.file import FileBase
from cipher.schemas.search import TextChunk


class EmailState(StrEnum):
    """Known folder / flag states inferred from ``X-Folder`` and related headers."""

    ARCHIVED = "archived"
    DELETED = "deleted"
    DRAFT = "draft"
    FLAGGED = "flagged"
    SENT = "sent"
    SPAM = "spam"
    STARRED = "starred"

    @classmethod
    def from_folder(cls, folder: str | None) -> Self | None:
        """Get email state based on folder path."""
        if not folder:
            return None
        lower = folder.lower()
        _mapping: dict[str, EmailState] = {
            "archive": cls.ARCHIVED,
            "deleted": cls.DELETED,
            "draft": cls.DRAFT,
            "flag": cls.FLAGGED,
            "important": cls.FLAGGED,
            "sent": cls.SENT,
            "spam": cls.SPAM,
            "star": cls.STARRED,
        }
        return next((v for k, v in _mapping.items() if k in lower), None)


class EmailAddressDict(TypedDict, total=False):
    name: str | None
    address: str


class EmailAddress(BaseModel):
    name: str | None
    address: str


class EmailMetadata(BaseModel):
    sender: EmailAddress | None = Field(
        default=None, description="Sender if email is sent on behalf of someone else."
    )
    sent_from: EmailAddress = Field(alias="from")
    sent_to: list[EmailAddress] = Field(default_factory=list, alias="to")
    cc: list[EmailAddress] = Field(default_factory=list)
    bcc: list[EmailAddress] = Field(default_factory=list)
    subject: str | None = Field(
        default=None, serialization_alias="title"
    )  # for search indexing
    date_sent: datetime | None = None
    conversation_id: str | None = None
    state: EmailState | None = None
    message_id: str | None = None
    labels: list[str] = Field(
        default_factory=list, description="Labels or folders associated with the email"
    )

    model_config = {"populate_by_name": True}


class EmailBase(BaseModel):
    """Parsed representation of a single RFC 2822 email message."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    plain: str | None = None
    html: str | None = None
    metadata: EmailMetadata

    # Polymorphic: enriched objects if file_typer is used, else Paths
    attachments: list[FileBase | Path] = Field(default_factory=list)

    meaningful_hash: str | None = None
    raw_header: dict[str, str] | None = None

    model_config = {"populate_by_name": True}


class EmailTextChunk(EmailMetadata, TextChunk):
    """Searchable chunk of an email, inheriting metadata for filtering."""

    pass
