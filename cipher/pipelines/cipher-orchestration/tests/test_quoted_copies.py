from datetime import UTC, datetime

from cipher.orchestration.quoted_copies import QuotedCopies, _letters, _OwnMessage
from cipher.schemas.content.email import EmailMetadata, QuotedBlock, QuoteKind
from cipher.schemas.content.extraction import ExtractedText, TextExtractor

REPLY = (
    "Tuesday works for me.\n\n"
    "On Mon, Jul 21, 2025 at 7:28 AM Megan Flick <megan@x.com> wrote:\n"
    "> Can we meet Tuesday to sign the lease with Dolce Realty?\n\n"
    "On Sun, Jul 20, 2025 at 9:00 PM Nick B <nick@y.com> wrote:\n"
    "> ok\n"
)


def _reply() -> ExtractedText:
    first = REPLY.index("On Mon")
    second = REPLY.index("On Sun")
    blocks = [
        QuotedBlock(start_offset=first, end_offset=second - 2, kind=QuoteKind.REPLY, from_address="megan@x.com"),
        QuotedBlock(start_offset=second, end_offset=len(REPLY) - 1, kind=QuoteKind.REPLY, from_address="nick@y.com"),
    ]
    metadata = EmailMetadata(conversation_id="thread-1", quoted_blocks=blocks)
    now = datetime.now(UTC)
    return ExtractedText(
        id="t3",
        file_id="reply",
        content=REPLY,
        extractor=TextExtractor.PYPARSE,
        metadata=metadata,
        date_created=now,
        date_last_updated=now,
    )


def _own(file_id: str, address: str, text: str) -> _OwnMessage:
    return _OwnMessage(file_id=file_id, from_address=address, opening=_letters(text)[:60])


def test_quoted_copy_of_an_email_in_the_dataset_is_blanked_in_place():
    """Megan's message is its own file, so its quoted copy is skipped; offsets and lines don't move."""
    megan = _own("megan-email", "megan@x.com", "Can we meet Tuesday to sign the lease with Dolce Realty?")
    masked = QuotedCopies({"thread-1": [megan]}).mask(_reply())
    assert len(masked) == len(REPLY) and masked.count("\n") == REPLY.count("\n")
    assert "Megan Flick" not in masked and "Dolce" not in masked
    assert masked.startswith("Tuesday works for me.") and "Nick B" in masked


def test_only_copy_and_other_authors_are_kept():
    """A quoted message with no file of its own is the only copy; the same words from someone else aren't a copy."""
    impostor = _own("other", "someone@z.com", "Can we meet Tuesday to sign the lease with Dolce Realty?")
    assert QuotedCopies({"thread-1": [impostor]}).covered(_reply()) == []
    assert QuotedCopies({}).mask(_reply()) == REPLY


def test_short_message_must_end_the_block_and_match_its_author():
    """`ok` is too short to search for, so it counts only as the whole end of its author's block."""
    nick = _own("nick-email", "nick@y.com", "ok")
    reply = _reply()
    assert QuotedCopies({"thread-1": [nick]}).covered(reply) == [
        (reply.metadata.quoted_blocks[1].start_offset, len(REPLY) - 1)
    ]
    assert QuotedCopies({"thread-1": [_own("x", "megan@x.com", "ok")]}).covered(reply) == []
