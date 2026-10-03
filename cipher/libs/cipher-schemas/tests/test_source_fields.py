"""What the data itself says about a message: Gmail labels -> source tags + message states."""

from cipher.schemas.content.email import EmailCategory, EmailClient, EmailMetadata, MessageState
from cipher.schemas.content.extraction import ExtractedTextCreate


def test_folded_header_labels_and_bills():
    """A folded `X-Gmail-Labels` line still maps; `Category Bills` is a category."""
    labels = ["Category\n Updates", "Category Bills"]
    assert EmailCategory.for_email(EmailClient.GMAIL, labels) == [EmailCategory.UPDATES, EmailCategory.BILLS]


def test_gmail_keeps_every_state_most_definitive_first():
    """All states are kept; the single `state` is still the most definitive."""
    labels = ["Important", "Sent Messages", "Archived"]
    assert MessageState.all_from_gmail_labels(labels) == [
        MessageState.SENT,
        MessageState.FLAGGED,
        MessageState.ARCHIVED,
    ]
    assert MessageState.from_gmail_labels(labels) == MessageState.SENT
    assert MessageState.from_gmail_labels(["Inbox"]) is None


def test_extracted_text_source_fields():
    """Extracted text exposes the file's filterable copies."""
    gmail = EmailMetadata(email_client=EmailClient.GMAIL, labels=["Spam", "Category Promotions"])
    extracted = ExtractedTextCreate(file_id="f", content="", extractor="pyparse", metadata=gmail)
    assert extracted.source_tags() == ["promotions"]
    assert extracted.message_states() == ["spam"]

    outlook = EmailMetadata(email_client=EmailClient.OUTLOOK, state=MessageState.SENT)
    assert ExtractedTextCreate(file_id="f", content="", extractor="pyparse", metadata=outlook).message_states() == [
        "sent"
    ]
