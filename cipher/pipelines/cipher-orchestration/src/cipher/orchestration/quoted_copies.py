"""Quoted blocks that repeat an email the dataset already holds as its own file.

A reply carries its thread's history; when those earlier messages are in the dataset
too, extracting from the quoted copies counts every name once per reply (the 13k
"Megan Flick" mentions). Those blocks are blanked char-for-char before extraction, so
offsets stay valid. A quoted message with no file of its own is the only copy and is
always extracted.

A block is a copy of a message in the same conversation whose own text (before its
quotes) opens inside the block, compared on letters and digits only so quote markers
and re-wrapping don't matter; when both name an author, it must be the same. A message
too short to open anything ("Not yet") must end the block and have its author.
"""

import re
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import text

from cipher.schemas.content.email import EmailMetadata, QuotedBlock
from cipher.schemas.content.extraction import ExtractedText

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_OPENING_CHARS = 60
_MIN_OPENING_CHARS = 25
_OWN_TEXT_CHARS = 2000
_NON_WORD = re.compile(r"\W+")
_NOT_NEWLINE = re.compile(r"[^\n]")

_THREAD_EMAILS = text(
    """
    WITH thread_email AS (
        SELECT t.file_id, t.content, t.metadata, t.metadata->>'conversation_id' AS conversation_id
        FROM extracted_text t JOIN file f ON f.id = t.file_id
        WHERE f.dataset_id = :dataset_id AND f.filetype_group = 'email' AND t.metadata ? 'conversation_id'
    )
    SELECT file_id, conversation_id, lower(metadata->'sent_from'->>'value') AS from_address,
           left(content, coalesce((metadata->'quoted_blocks'->0->>'start_offset')::int, :own_chars)) AS own_text
    FROM thread_email
    WHERE conversation_id IN (
        SELECT conversation_id FROM thread_email WHERE conversation_id IS NOT NULL
        GROUP BY conversation_id HAVING count(*) > 1
    )
    """
)


class _OwnMessage(NamedTuple):
    file_id: str
    from_address: str | None
    opening: str


def _letters(value: str) -> str:
    return _NON_WORD.sub("", value.lower())


def _is_copy(message: _OwnMessage, quoted: str, author: str | None) -> bool:
    """Its opening is in the block; a short message (`ok`, `Not yet`) must be the block's whole end, by its author."""
    if len(message.opening) < _MIN_OPENING_CHARS:
        return author is not None and message.from_address == author and quoted.endswith(message.opening)
    return message.opening in quoted and (author is None or message.from_address in (None, author))


def opening(own_text: str) -> str:
    """A message's comparable opening: letters and digits of its own text (before its quotes)."""
    return _letters(own_text[:_OWN_TEXT_CHARS])[:_OPENING_CHARS]


class QuotingEmail(NamedTuple):
    """An email reduced to what quote matching compares: its own opening and the blocks it quotes."""

    message: _OwnMessage
    quoted: list[tuple[str, str | None]]  # (letters of each quoted block, the block's author address)


def quoting_email(file_id: str, content: str, blocks: list[QuotedBlock], from_address: str | None) -> QuotingEmail:
    """Prepare an email for `linked_by_quotes` from its text and quoted blocks."""
    own_text = content[: blocks[0].start_offset] if blocks else content
    return QuotingEmail(
        message=_OwnMessage(file_id, (from_address or "").lower() or None, opening(own_text)),
        quoted=[
            (_letters(content[block.start_offset : block.end_offset]), (block.from_address or "").lower() or None)
            for block in blocks
        ],
    )


def _quotes(email: QuotingEmail, other: QuotingEmail) -> bool:
    return bool(other.message.opening) and any(
        _is_copy(other.message, quoted, author) for quoted, author in email.quoted
    )


def linked_by_quotes(members: list[QuotingEmail], candidates: list[QuotingEmail]) -> list[QuotingEmail]:
    """The candidates that quote, or are quoted by, a member -- followed transitively through the chain.

    Args:
        members: Emails already in the conversation.
        candidates: Emails that might belong (e.g. the same subject, close in time).

    Returns:
        The linked candidates, in their original order.
    """
    linked: list[QuotingEmail] = []
    group, remaining = list(members), list(candidates)
    while joined := [c for c in remaining if any(_quotes(c, m) or _quotes(m, c) for m in group)]:
        linked += joined
        group += joined
        remaining = [c for c in remaining if c not in joined]
    return [c for c in candidates if c in linked]


class QuotedCopies:
    """Each multi-email conversation's messages, to recognise their quoted copies."""

    def __init__(self, conversations: dict[str, list[_OwnMessage]]) -> None:
        self._conversations = conversations

    @classmethod
    async def load(cls, session: "AsyncSession", dataset_id: str) -> "QuotedCopies":
        """Index the dataset's conversations that have more than one email."""
        conversations: dict[str, list[_OwnMessage]] = {}
        rows = await session.execute(_THREAD_EMAILS, {"dataset_id": dataset_id, "own_chars": _OWN_TEXT_CHARS})
        for file_id, conversation_id, from_address, own_text in rows:
            if own_opening := opening(own_text):
                conversations.setdefault(conversation_id, []).append(_OwnMessage(file_id, from_address, own_opening))
        return cls(conversations)

    def covered(self, extracted: ExtractedText) -> list[tuple[int, int]]:
        """Offsets of this text's quoted blocks whose message is in the dataset as its own email."""
        metadata = extracted.metadata
        if not isinstance(metadata, EmailMetadata) or not metadata.quoted_blocks:
            return []
        others = [
            message
            for message in self._conversations.get(metadata.conversation_id or "", [])
            if message.file_id != extracted.file_id
        ]
        ranges = []
        for block in metadata.quoted_blocks:
            quoted = _letters(extracted.content[block.start_offset : block.end_offset])
            author = (block.from_address or "").lower() or None
            if any(_is_copy(message, quoted, author) for message in others):
                ranges.append((block.start_offset, block.end_offset))
        return ranges

    def mask(self, extracted: ExtractedText) -> str:
        """The text with covered quoted blocks blanked (newlines kept, so lines and offsets don't move)."""
        content = extracted.content
        for start, end in self.covered(extracted):
            content = content[:start] + _NOT_NEWLINE.sub(" ", content[start:end]) + content[end:]
        return content
