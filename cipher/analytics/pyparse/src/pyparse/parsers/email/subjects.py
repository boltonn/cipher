"""Subject lines without their reply / forward prefixes, to group emails whose headers don't link them."""

import re
from typing import Final

_PREFIXES: Final[str] = "|".join(
    [
        "re",
        "aw",
        "sv",
        "vs",
        "antw",
        "odp",
        "ynt",
        "rif",
        "res",
        "отв",
        "ответ",
        "відп",
        "回复",
        "答复",
        "回覆",
        "答覆",
        "返信",
        "رد",
        "پاسخ",
        "fwd?",
        "wg",
        "tr",
        "rv",
        "enc",
        "doorst",
        "пересл",
        "переслать",
        "転送",
        "转发",
        "轉寄",
        "转寄",
        "ارسال",
        "إعادة توجيه",
    ]
)
_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    rf"^\s*(?:{_PREFIXES})\s*(?:\[\d+\]|\^\d+|\(\d+\))?\s*[:：]\s*", re.IGNORECASE
)
_SPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_MIN_KEY_CHARS: Final[int] = 4


def strip_reply_prefixes(subject: str) -> tuple[str, bool]:
    """The subject without its leading reply / forward prefixes, and whether it had any.

    Args:
        subject: The subject line as sent.

    Returns:
        The remaining subject (stripped) and True when at least one prefix was removed.
    """
    remaining, had_prefix = subject, False
    while match := _PREFIX_RE.match(remaining):
        remaining, had_prefix = remaining[match.end() :], True
    return remaining.strip(), had_prefix


def subject_key(subject: str | None) -> str | None:
    """A comparable key for a subject: prefixes removed, casefolded, spacing collapsed.

    Args:
        subject: The subject line as sent.

    Returns:
        The key, or None when too little is left to tell conversations apart ("Re:", "hi").
    """
    if not subject:
        return None
    key = _SPACE_RE.sub(" ", strip_reply_prefixes(subject)[0]).casefold().strip(" -–—:.!?")
    return key if len(key) >= _MIN_KEY_CHARS else None
