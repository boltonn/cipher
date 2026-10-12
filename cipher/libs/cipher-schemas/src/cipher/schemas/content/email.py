from __future__ import annotations

from datetime import datetime
from typing import Literal, Self, TypedDict

from pydantic import Field, field_validator

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas.content.search import CorrespondenceFilters, MentionSpan, TextChunk
from cipher.schemas.ingestion.file import FileBase


class EmailClient(StrEnum):
    """Which mailbox export produced this .eml -- each has its own status/label convention.

    Detected from characteristic headers rather than trusted metadata, since
    nothing in an .eml file self-identifies its exporting client. Add a new
    member (plus a header fingerprint in `detect` and a mapping in
    `MessageState`) once a real sample confirms that client's convention --
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


def _normalized_labels(labels: list[str]) -> set[str]:
    r"""Lowercased labels with folded-header whitespace collapsed (`Category\n Updates` -> `category updates`)."""
    return {" ".join(label.split()).lower() for label in labels}


class MessageState(StrEnum):
    """Uniform status vocabulary for a message (email now; SMS / chat apps later), as its source recorded it.

    Each source client exposes status through completely different headers
    (Outlook/Exchange: a single `X-Folder` path; Gmail: a comma-separated
    `X-Gmail-Labels` list where several labels can apply at once) -- these
    values are what a UI actually filters/displays on, independent of which
    client produced the message.
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
        _mapping: dict[str, MessageState] = {
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
    def all_from_gmail_labels(cls, labels: list[str]) -> list[Self]:
        """Gmail: every state its `X-Gmail-Labels` carry, most definitive first.

        A location label (trash/spam/draft/sent) ranks above a flag label
        (starred/important), and `Archived` (Gmail's "All Mail, no Inbox label")
        is last. `Sent Messages` / `Deleted Messages` are IMAP folders synced in as labels.
        """
        lowered = _normalized_labels(labels)
        _priority: list[tuple[set[str], MessageState]] = [
            ({"trash", "deleted messages"}, cls.DELETED),
            ({"spam"}, cls.SPAM),
            ({"draft", "drafts"}, cls.DRAFT),
            ({"sent", "sent messages"}, cls.SENT),
            ({"starred"}, cls.STARRED),
            ({"important"}, cls.FLAGGED),
            ({"archived"}, cls.ARCHIVED),
        ]
        return [state for names, state in _priority if names & lowered]

    @classmethod
    def from_gmail_labels(cls, labels: list[str]) -> Self | None:
        """Gmail: the single most definitive state (see `all_from_gmail_labels`); None for plain `Inbox`."""
        return next(iter(cls.all_from_gmail_labels(labels)), None)


class EmailCategory(StrEnum):
    """Uniform inbox-category vocabulary (the mail client's own classifier) every `EmailClient` maps onto.

    Gmail tabs messages with `Category *` labels; other clients' conventions get a
    mapper here once a real sample confirms them (see `EmailClient`). Several can
    apply at once (Gmail tags an order receipt both Purchases and Updates). Stored
    on the file as **source tags**.
    """

    PERSONAL = "personal"
    SOCIAL = "social"
    PROMOTIONS = "promotions"
    UPDATES = "updates"
    FORUMS = "forums"
    PURCHASES = "purchases"
    TRAVEL = "travel"
    BILLS = "bills"

    @classmethod
    def from_gmail_labels(cls, labels: list[str]) -> list[Self]:
        """Gmail: `Category Promotions` etc. in `X-Gmail-Labels`."""
        lowered = _normalized_labels(labels)
        return [category for category in cls if f"category {category.value}" in lowered]

    @classmethod
    def for_email(cls, client: EmailClient, labels: list[str]) -> list[Self]:
        """The client's categories for an email in the common vocabulary; empty when the client has none."""
        if client == EmailClient.GMAIL:
            return cls.from_gmail_labels(labels)
        return []


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

    @field_validator("name", mode="before")
    @classmethod
    def _clean_name(cls, name: str | None) -> str | None:
        """Strip wrapping quotes (Outlook's `'Nick Bolton'`); none when the name is just an address.

        `"bolton213@yahoo.com" <bolton213@yahoo.com>` carries no name.
        """
        name = " ".join((name or "").split()).strip("'\"`").strip()
        return None if not name or ("@" in name and " " not in name) else name


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


class MeaningfulHashSource(StrEnum):
    """What an email's meaningful hash was computed from."""

    MESSAGE_ID = "message_id"
    CONTENT = "content"


class QuoteKind(StrEnum):
    """How an earlier message came to sit inside this email's text."""

    REPLY = "reply"
    FORWARD = "forward"


class QuotedBlock(BaseModel):
    """An earlier message carried inside this email's text -- a reply's quoted history or a forward.

    Offsets index the extracted text; the block runs from its attribution
    ("On Mon, Megan <m@x.com> wrote:", "-----Original Message-----", "От: ...")
    to where the next quoted message starts or the quote ends.
    """

    start_offset: int
    end_offset: int
    kind: QuoteKind
    attribution: str | None = Field(default=None, description="The line(s) introducing the quote, as written")
    from_name: str | None = None
    from_address: str | None = None
    date_sent: datetime | None = Field(
        default=None, description="Parsed only when the attribution writes it in English/RFC form"
    )


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
    conversation_id: str | None = Field(
        default=None,
        description="The client's thread id (Gmail/Outlook), else the thread's root Message-ID from References/In-Reply-To",
    )
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list, description="Message-IDs of the thread so far, oldest first")
    quoted_blocks: list[QuotedBlock] = Field(default_factory=list)
    email_client: EmailClient = Field(
        default=EmailClient.UNKNOWN, description="Mailbox export this email's status/label headers follow"
    )
    state: MessageState | None = None
    message_id: str | None = None
    meaningful_hash: str | None = Field(
        default=None,
        description="Same for every copy of one message (an inbox and a Sent folder, two mailboxes): "
        "from the Message-ID, else from sender, To/Cc, date, subject and opening text",
    )
    meaningful_hash_source: MeaningfulHashSource | None = Field(default=None)
    labels: list[str] = Field(default_factory=list, description="Labels or folders associated with the email")
    categories: list[EmailCategory] = Field(
        default_factory=list, description="The mail client's inbox categories (promotions, social, ...)"
    )

    model_config = {"populate_by_name": True}

    def client_categories(self) -> list[EmailCategory]:
        """`categories`, or derived from `labels` for emails parsed before categories were stored."""
        return self.categories or EmailCategory.for_email(self.email_client, self.labels)

    def message_states(self) -> list[MessageState]:
        """Every state the source recorded (Gmail labels can carry several), plus the parsed `state`."""
        states = MessageState.all_from_gmail_labels(self.labels) if self.email_client == EmailClient.GMAIL else []
        return states if not self.state or self.state in states else [self.state, *states]


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
    is_encrypted: bool = Field(
        default=False,
        description="Its body needs a key (S/MIME encrypted, IPM.Note.SMIME); its headers were still read",
    )

    attachments: list[FileBase] = Field(
        default_factory=list,
        description="True attachments, as the parser's sink returned them (path / uri set when stored); "
        "not the images the body shows inline",
    )

    raw_header: dict[str, str] | None = None

    model_config = {"populate_by_name": True}


class ConversationSource(StrEnum):
    """How a conversation's emails were found."""

    HEADERS = "headers"  # `conversation_id` from the client's thread id / References / In-Reply-To
    QUOTED_TEXT = "quoted_text"  # also emails the headers miss: same subject, within 30 days, one quotes the other


class ConversationEmail(BaseModel):
    """One email in a conversation, as listed beside the open email."""

    file_id: str
    title: str | None = None
    from_name: str | None = None
    from_address: str | None = None
    date_sent: datetime | None = None
    preview: str = Field(default="", description="Opening of the text this email adds, quoted history excluded")


class EmailConversation(BaseModel):
    """The emails of one conversation in `date_sent` order, copies of one message listed once."""

    conversation_id: str | None = None
    source: ConversationSource = ConversationSource.HEADERS
    emails: list[ConversationEmail] = Field(default_factory=list)


class EmailTextChunk(EmailMetadata, TextChunk):
    """Searchable chunk of an email, inheriting metadata for filtering.

    `filetype_group` discriminates document vs. email chunks living side by
    side in the same unified `text_chunks` index/search surface.
    """

    filetype_group: Literal["email"] = "email"


class ScoredEmailTextChunk(EmailTextChunk):
    """An `EmailTextChunk` decorated with its Elasticsearch retrieval score."""

    score: float = Field(..., description="Retrieval score from Elasticsearch")
    highlights: list[str] = Field(
        default_factory=list,
        description="Matched words/phrases from Elasticsearch highlighting; empty for pure kNN results",
    )
    mention_spans: list[MentionSpan] = Field(
        default_factory=list, description="Mentions of the filtered entities inside this chunk"
    )


class EmailCountGroupBy(StrEnum):
    """How `EmailCountRequest` buckets the matching emails."""

    SENDER = "sender"
    RECIPIENT = "recipient"
    CORRESPONDENT = "correspondent"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"


class EmailCountRequest(CorrespondenceFilters):
    """Count emails matching correspondence filters, grouped by a party or a period.

    Emails are counted once per message (`message_id`, else content hash), so
    the same message in several mailboxes isn't double counted. Party buckets
    exclude the filtered entities themselves -- `sent_from=[x]` grouped by
    `recipient` is "who does x email the most".
    """

    dataset_id: str | None = None
    dataset_ids: list[str] | None = Field(
        default=None, description="Restrict to any of these datasets (set server-side to the caller's access)"
    )
    group_by: EmailCountGroupBy = EmailCountGroupBy.CORRESPONDENT
    limit: int = Field(default=20, ge=1, le=500)


class EmailCountBucket(BaseModel):
    """One party or period and how many emails fall in it."""

    key: str = Field(description="Entity id for a party bucket; 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD' for a period")
    label: str = Field(description="Entity display name or the period")
    entity_type: str | None = None
    addresses: list[str] = Field(default_factory=list, description="Email addresses this party used in these emails")
    email_count: int
    date_first: datetime | None = None
    date_last: datetime | None = None


class EmailCounts(BaseModel):
    total_emails: int = Field(description="Distinct emails matching the filters")
    group_by: EmailCountGroupBy
    buckets: list[EmailCountBucket] = Field(default_factory=list)
