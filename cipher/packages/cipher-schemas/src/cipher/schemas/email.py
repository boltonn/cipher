from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self, TypedDict

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.file import FileBase
from cipher.schemas.search import TextChunk


class EmailClient(StrEnum):
    """Which mailbox export produced this .eml -- each has its own status/label convention.

    Detected from characteristic headers rather than trusted metadata, since
    nothing in an .eml file self-identifies its exporting client. Add a new
    member (plus a header fingerprint in `detect` and a mapping in
    `EmailState`) once a real sample confirms that client's convention --
    guessing at unseen header formats (e.g. Yahoo/Yandex, not yet observed
    in any sample data) risks silently mis-tagging state.
    """

    GMAIL = "gmail"
    OUTLOOK = "outlook"
    UNKNOWN = "unknown"

    @classmethod
    def detect(cls, headers: dict[str, str]) -> Self:
        """Identify the exporting client from a lowercased header-name dict."""
        if "x-gmail-labels" in headers or "x-gm-thrid" in headers:
            return cls.GMAIL
        if "x-folder" in headers or "x-origin" in headers:
            return cls.OUTLOOK
        return cls.UNKNOWN


class EmailState(StrEnum):
    """Uniform status vocabulary every `EmailClient`'s own convention maps onto.

    Each source client exposes status through completely different headers
    (Outlook/Exchange: a single `X-Folder` path; Gmail: a comma-separated
    `X-Gmail-Labels` list where several labels can apply at once) -- these
    values are what a UI actually filters/displays on, independent of which
    client produced the email.
    """

    ARCHIVED = "archived"
    DELETED = "deleted"
    DRAFT = "draft"
    FLAGGED = "flagged"
    SENT = "sent"
    SPAM = "spam"
    STARRED = "starred"

    @classmethod
    def from_folder(cls, folder: str | None) -> Self | None:
        r"""Outlook/Exchange: infer state from an `X-Folder` path, e.g. ``\Sent Items``."""
        if not folder:
            return None
        lower = folder.lower()
        _mapping: dict[str, EmailState] = {
            "archive": cls.ARCHIVED,
            "deleted": cls.DELETED,
            "trash": cls.DELETED,
            "draft": cls.DRAFT,
            "flag": cls.FLAGGED,
            "important": cls.FLAGGED,
            "sent": cls.SENT,
            "spam": cls.SPAM,
            "junk": cls.SPAM,
            "star": cls.STARRED,
        }
        return next((v for k, v in _mapping.items() if k in lower), None)

    @classmethod
    def from_gmail_labels(cls, labels: list[str]) -> Self | None:
        r"""Gmail: infer state from `X-Gmail-Labels`.

        Several labels can apply to one message at once (e.g. `Starred` and
        `Category Promotions` together), so this picks the most definitive
        single state in priority order -- a location label (trash/spam/
        draft/sent) beats a flag label (starred/important), and `Archived`
        (Gmail's "All Mail, no Inbox label" state) is the lowest-priority
        fallback. A plain `Inbox` label (no special state) yields None, same
        as an Outlook `X-Folder` of `\Inbox` does via `from_folder`.
        """
        if not labels:
            return None
        lowered = {label.lower() for label in labels}
        _priority: list[tuple[str, EmailState]] = [
            ("trash", cls.DELETED),
            ("spam", cls.SPAM),
            ("draft", cls.DRAFT),
            ("sent", cls.SENT),
            ("starred", cls.STARRED),
            ("important", cls.FLAGGED),
            ("archived", cls.ARCHIVED),
        ]
        return next((state for label, state in _priority if label in lowered), None)


class ParticipantType(StrEnum):
    """What kind of contact string a `Participant.value` holds."""

    EMAIL = "email"
    PHONE = "phone"


class NamedParticipant(BaseModel):
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


class EmailAddress(NamedParticipant):
    """A participant whose contact string is an email address.

    This subclass exists to support a `value` field with a more specific
    type than the generic `Participant.value` -- a `str` that passes
    `email_validator.validate_email`.
    """

    type: Literal[ParticipantType.EMAIL] = ParticipantType.EMAIL


class NamedParticipantDict(TypedDict, total=False):
    name: str | None
    value: str


class EmailMetadata(BaseModel):
    """Email-specific metadata, denormalized onto every chunk of that email."""

    title: str | None = Field(default=None, description="Subject line")
    sender: EmailAddress | None = Field(default=None, description="Sender if email is sent on behalf of someone else.")
    sent_from: EmailAddress | None = Field(
        default=None,
        alias="from",
        description="Sender, if this email has one -- some system-generated records "
        "(e.g. Lotus Notes organizer/calendar entries swept into an export) have no From header at all.",
    )
    sent_to: list[EmailAddress] = Field(default_factory=list, alias="to")
    cc: list[EmailAddress] = Field(default_factory=list)
    bcc: list[EmailAddress] = Field(default_factory=list)
    date_sent: datetime | None = None
    conversation_id: str | None = None
    email_client: EmailClient = Field(
        default=EmailClient.UNKNOWN, description="Mailbox export this email's status/label headers follow"
    )
    state: EmailState | None = None
    message_id: str | None = None
    labels: list[str] = Field(default_factory=list, description="Labels or folders associated with the email")

    model_config = {"populate_by_name": True}


class EmailBase(BaseModel):
    """Parsed representation of a single RFC 2822 email message.

    Has no ``id`` of its own -- this is a computed view derived on demand
    from an ingested ``File``'s bytes, not a persisted entity, so its
    identity is that ``File``'s id. Callers that need to correlate a parse
    result back to a file already have that file's id in scope.
    """

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
