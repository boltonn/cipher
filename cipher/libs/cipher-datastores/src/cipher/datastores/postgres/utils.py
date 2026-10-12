import re
import unicodedata
from typing import Any

_WS_RE = re.compile(r"\s+")
_QUOTES = "'\"`\u2018\u2019\u201a\u201c\u201d\u201e\u00ab\u00bb\u2039\u203a"
_POSSESSIVE_RE = re.compile(r"(?<=[\w.])['\u2019\u02bc][sS]$")
# Name-key folding: one apostrophe glyph; punctuation, dashes and brackets are word breaks
_APOSTROPHES = str.maketrans(dict.fromkeys("`\u2018\u2019\u02bc\u2032", "'"))
_BREAK_RE = re.compile(
    r"[\s.,;:|/\\()\[\]{}<>\"\u201a\u201c\u201d\u201e\u00ab\u00bb\u2039\u203a!?*_~\u2022\u00b7\u2010-\u2015\u2212\u2043-]+"
)
_KEY_POSSESSIVE_RE = re.compile(r"(?<=\w) ?'s$")  # after breaks, `Inc.'s` reads `inc 's`
_AMPERSAND_RE = re.compile(r"\s*&\s*")
_INITIALS_RE = re.compile(r"\b(?:[^\W\d_] ){1,}[^\W\d_]\b")
# variation selectors, Khmer inherent vowels, Hangul fillers: letter-class but invisible
_INVISIBLE_RE = re.compile("[\ufe00-\ufe0f\U000e0100-\U000e01ef\u17b4\u17b5\u115f\u1160\u3164\uffa0]")
# invisible format/control/private-use chars (spam obfuscation) and symbols like ® ™ ⚽
_DROPPED_CATEGORIES = frozenset({"Cf", "Cc", "Cn", "Co", "Cs", "So", "Sk"})
# Words around a name that never tell two things apart. Short forms that are also name parts
# (`co`, `sa`, `ag`, `as`) are left alone.
_LEGAL_SUFFIXES = frozenset(
    {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "plc", "gmbh", "llp"}
)
_LEGAL_PREFIXES = frozenset({"the", "ооо", "оао", "зао", "пао", "тов", "mr", "mrs", "ms", "miss", "dr", "prof"})
_MAILBOX_SUFFIXES = (("no", "reply"), ("noreply",), ("do", "not", "reply"), ("donotreply",))


def _reading_order(value: str) -> str:
    """`Strosser, Stephen` -> `Stephen Strosser` -- a person written surname first.

    Only `Surname, Given [Middle]` shapes: one comma, short sides, no legal form or state
    code after it (`Roku, Inc`, `Newark, NJ` stay as written).
    """
    if value.count(",") != 1:
        return value
    left, right = (part.strip() for part in value.split(","))
    left_words, right_words = left.split(), right.split()
    if not (1 <= len(left_words) <= 2 and 1 <= len(right_words) <= 2):
        return value
    state_code = len(right_words) == 1 and right.isupper() and len(right) <= 3
    if state_code or right.casefold().strip(".") in _LEGAL_SUFFIXES:
        return value
    return f"{right} {left}"


def _drop_affixes(words: str) -> str:
    """`the paypal inc` -> `paypal`, `adaire no reply` -> `adaire`; never down to nothing."""
    tokens = words.split(" ")
    changed = True
    while changed:
        changed = False
        for suffix in _MAILBOX_SUFFIXES:
            if len(tokens) > len(suffix) and tuple(tokens[-len(suffix) :]) == suffix:
                tokens, changed = tokens[: -len(suffix)], True
        if len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
            tokens, changed = tokens[:-1], True
        if len(tokens) > 1 and tokens[0] in _LEGAL_PREFIXES:
            tokens, changed = tokens[1:], True
    return " ".join(tokens)


def normalize_name(value: str) -> str:
    """Fold a name into its name-group key, so spellings that differ only in formatting group together.

    Accents are removed (NFKD, combining marks dropped) and the result casefolded;
    non-Latin scripts (Cyrillic, Han) are otherwise left intact -- fuzzy matching
    there relies on the name embedding. On top of that, every difference seen not
    to matter in real data is folded away:

    * quotes and brackets anywhere, and a trailing possessive (`"Nick Bolton's"`)
    * punctuation and dash variants as word breaks (`Roku, Inc.`, `Asia-Pacific`, `7‐Eleven`, `Yahoo! Mail`)
    * spaced initials joined (`J. K. Rowling` = `J.K. Rowling` = `JK Rowling`)
    * apostrophe glyphs (`O’Reilly` = `O'Reilly`), spacing around `&`
    * invisible format characters and symbols (`Indigo® Mastercard®`, emoji)
    * a trailing legal form or mailbox label and a leading `the` or title (`The PayPal, Inc.` =
      `PayPal`, `Adaire (no reply)` = `Adaire`, `Mr. Bolton` = `Bolton`)
    * a person written surname first (`Strosser, Stephen` = `Stephen Strosser`)

    The key is the resolution unit: everything sharing it is one name, whatever its type.
    """
    # whitespace first: a line break or tab is a word break, not a control character to drop
    spaced = _WS_RE.sub(" ", value)
    decomposed = unicodedata.normalize("NFKD", _reading_order(_INVISIBLE_RE.sub("", spaced)).translate(_APOSTROPHES))
    kept = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch) and unicodedata.category(ch) not in _DROPPED_CATEGORIES
    )
    folded = unicodedata.normalize("NFKC", kept).casefold()
    words = _AMPERSAND_RE.sub(" & ", _BREAK_RE.sub(" ", folded)).strip(" '")
    words = _INITIALS_RE.sub(lambda initials: initials.group().replace(" ", ""), words)
    words = _drop_affixes(_KEY_POSSESSIVE_RE.sub("", words).strip(" '"))
    return words or _WS_RE.sub(" ", value.casefold()).strip()


def trim_name_span(surface: str) -> tuple[int, int]:
    """`(start, end)` of `surface` without surrounding quotes/whitespace or a trailing possessive.

    Unlike `normalize_name` it keeps dots and brackets (`Acme Inc.`), so the trimmed span
    is still the name as written.
    """
    start, end = 0, len(surface)
    for _ in range(2):
        while start < end and (surface[start] in _QUOTES or surface[start].isspace()):
            start += 1
        while end > start and (surface[end - 1] in _QUOTES or surface[end - 1].isspace()):
            end -= 1
        if possessive := _POSSESSIVE_RE.search(surface, start, end):
            end = possessive.start()
    return (start, end) if start < end else (0, len(surface))


def strip_null_bytes(value: Any) -> Any:
    """Recursively strip NUL (0x00) bytes from strings, dicts, and lists.

    Postgres text/JSONB columns reject embedded NUL bytes outright, but
    extracted content (HTML emails, PDFs, legacy encodings) sometimes
    contains them -- this sanitizes a value tree before it reaches asyncpg.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {key: strip_null_bytes(item) for key, item in value.items()}
    if isinstance(value, list):
        return [strip_null_bytes(item) for item in value]
    return value
