"""An email's meaningful hash: the same for every copy of one message, whatever mailbox it came from.

The file's own sha256 differs per copy (Received, Delivered-To, labels, folder), so copies of
one message -- the recipient's inbox and the sender's Sent folder, two people on one server --
are matched on what the message says instead:

* its `Message-ID`, when it has one (`message_id`);
* otherwise (`content`) the sender's address, the To and Cc addresses (sorted), the send time
  to the second (UTC), the subject, and the first 2,000 letters and digits of the body. Bcc is
  left out (only the sender's copy has it), as are links (mail gateways rewrite them), the end of
  a long body (gateways append disclaimers), and `[EXTERNAL]`-style tags added to the subject.
  Case, spacing and punctuation are ignored. `RE:` / `FW:` stay: they mark a different message.
"""

import hashlib
import re
from datetime import datetime

from cipher.schemas.content.email import MeaningfulHashSource

_BODY_CHARS = 2000
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_NON_WORD = re.compile(r"\W+")
_SUBJECT_TAGS = re.compile(r"^\s*(?:(?:\[[^\]]{1,40}\]|\*{0,2}external\*{0,2}:?)\s*)+", re.IGNORECASE)


def meaningful_hash(metadata: dict, body: str | None) -> tuple[str, MeaningfulHashSource] | None:
    """The hash and what it came from, or None when there is neither a Message-ID nor a sender and date.

    Args:
        metadata: Parsed email metadata (`extract_metadata` keys).
        body: The body as text (plain, or the HTML's text).
    """
    if message_id := metadata.get("message_id"):
        return _sha256("message_id", message_id.strip().strip("<>")), MeaningfulHashSource.MESSAGE_ID
    sender, date_sent = _address(metadata.get("from")), metadata.get("date_sent")
    if not sender or not isinstance(date_sent, datetime):
        return None
    recipients = sorted(filter(None, map(_address, [*metadata.get("to", []), *metadata.get("cc", [])])))
    subject = " ".join(_SUBJECT_TAGS.sub("", metadata.get("title") or "").lower().split())
    text = _NON_WORD.sub("", _URL.sub(" ", body or "").lower())[:_BODY_CHARS]
    parts = (sender, ",".join(recipients), str(int(date_sent.timestamp())), subject, text)
    return _sha256("content", *parts), MeaningfulHashSource.CONTENT


def _address(participant: object) -> str | None:
    value = participant.get("value") if isinstance(participant, dict) else getattr(participant, "value", None)
    return value.strip().lower() if value else None


def _sha256(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
