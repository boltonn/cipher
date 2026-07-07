from pathlib import Path

from cipher.schemas.email import EmailBase
from pyparse.parsers.email.eml import EmlParser
from pyparse.parsers.email.msg import MsgParser

__all__ = ["EmlParser", "MsgParser", "SUPPORTED_FILETYPES", "parse_email"]

# Filetype names (matching filetyper's registry `name` field, group "email")
# that this package can parse. Kept here rather than in a shared registry --
# which analytic supports which filetype is this analytic's own concern.
SUPPORTED_FILETYPES = frozenset({"eml", "outlook"})


def parse_email(
    source: bytes | str | Path,
    filetype: str,
    *,
    extract_children: bool = False,
    out_dir: Path | None = None,
) -> EmailBase:
    """Parse an email file, dispatching to the parser for its filetype.

    `filetype` is filetyper's registry name for the file ("eml" or "outlook"
    for .msg), not the raw file extension. `extract_children`/`out_dir`
    write attachment payloads to disk and populate each attachment's
    `path`/`uri`, letting callers persist them as their own `File` rows.
    """
    if filetype == "eml":
        return EmlParser().parse(source, extract_children=extract_children, out_dir=out_dir)
    if filetype == "outlook":
        return MsgParser().parse(source, extract_children=extract_children, out_dir=out_dir)
    raise ValueError(
        f"No email parser for filetype {filetype!r}; supported: {sorted(SUPPORTED_FILETYPES)}"
    )
