from typing import Any


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
