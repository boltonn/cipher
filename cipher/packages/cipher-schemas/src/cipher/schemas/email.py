from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self, TypedDict
from uuid import uuid4

from pydantic import Field

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


class ParticipantType(StrEnum):
    """What kind of contact string a `Participant.value` holds."""

    EMAIL = "email"
    PHONE = "phone"


class Participant(BaseModel):
    """A named party identified by a single, typed contact string.

    Shared shape for "who" fields across content sources -- an email's
    sender/recipient (`type=email`) or, eventually, a message's
    sender/recipient (`type=phone`) -- self-describing rather than implied
    by which field it's sitting in, since participants from different
    sources can end up merged in one search result.
    """

    name: str | None = None
    type: ParticipantType
    value: str


class ParticipantDict(TypedDict, total=False):
    name: str | None
    type: ParticipantType
    value: str


class EmailMetadata(BaseModel):
    """Email-specific metadata, denormalized onto every chunk of that email."""

    title: str | None = Field(default=None, description="Subject line")
    sender: Participant | None = Field(default=None, description="Sender if email is sent on behalf of someone else.")
    sent_from: Participant = Field(alias="from")
    sent_to: list[Participant] = Field(default_factory=list, alias="to")
    cc: list[Participant] = Field(default_factory=list)
    bcc: list[Participant] = Field(default_factory=list)
    date_sent: datetime | None = None
    conversation_id: str | None = None
    state: EmailState | None = None
    message_id: str | None = None
    labels: list[str] = Field(default_factory=list, description="Labels or folders associated with the email")

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
    """Searchable chunk of an email, inheriting metadata for filtering.

    `filetype_group` discriminates document vs. email chunks living side by
    side in the same unified `text_chunks` index/search surface.
    """

    filetype_group: Literal["email"] = "email"


class ScoredEmailTextChunk(EmailTextChunk):
    """An `EmailTextChunk` decorated with its Elasticsearch retrieval score."""

    score: float = Field(..., description="Retrieval score from Elasticsearch")
