import re
import unicodedata
from typing import Any

_WS_RE = re.compile(r"\s+")


def normalize_name(value: str) -> str:
    """Fold a display name for trigram matching.

    Decomposes accents (NFKD, drops combining marks), casefolds, and collapses
    whitespace. Latin diacritics are removed; non-Latin scripts (Cyrillic, Han)
    are left intact -- fuzzy matching there relies on the name embedding.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WS_RE.sub(" ", stripped.casefold()).strip()


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
