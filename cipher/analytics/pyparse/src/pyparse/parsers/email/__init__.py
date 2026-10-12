"""Email files (.eml, Outlook .msg) into ``EmailBase``: ``parse_email`` picks the reader by filetype."""

from pathlib import Path

from cipher.schemas.content.email import EmailBase
from pyparse.children import ChildSink, describe_only
from pyparse.parsers.email.eml import EmailOptions, parse_eml
from pyparse.parsers.email.msg import parse_msg

__all__ = ["EmailOptions", "SUPPORTED_FILETYPES", "parse_email", "parse_eml", "parse_msg"]

# filetyper registry names (group "email") -> reader. Which analytic reads which filetype is its own concern.
READERS = {"eml": parse_eml, "outlook": parse_msg}
SUPPORTED_FILETYPES = frozenset(READERS)


def parse_email(
    source: bytes | str | Path,
    *,
    filetype: str,
    sink: ChildSink = describe_only,
    options: EmailOptions | None = None,
) -> EmailBase:
    """Parse an email file with the reader for its filetype.

    Args:
        source: Raw bytes, or a path to the file.
        filetype: filetyper's registry name ("eml", or "outlook" for .msg), not the extension.
        sink: Receives every child file (attachments, winmail.dat contents, inline images) and returns
            its record -- e.g. one that writes into the output store. Default: typed, bytes not kept.
        options: How to read it.

    Raises:
        ValueError: No reader for `filetype`.
    """
    if (reader := READERS.get(filetype)) is None:
        raise ValueError(f"No email reader for filetype {filetype!r}; supported: {sorted(SUPPORTED_FILETYPES)}")
    return reader(source, sink=sink, options=options)
