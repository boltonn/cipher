from collections.abc import Iterator
from mailbox import mbox
from pathlib import Path
from typing import Any

from loguru import logger

from pyparse.parsers.email import EmlParser


class MboxParser:
    """Parser for mbox files."""

    @staticmethod
    def stream(
        file_path: Path,
        return_raw_header: bool = True,
        extract_children: bool = False,
        out_dir: Path = None,
        **kwargs,
    ) -> Iterator[Any]:  # NOTE: placeholder for Email from Cipher.schemas.data.emails.email import Email
        """Stream an mbox file."""
        msg_generator = mbox(file_path)
        logger.info(f"Found {len(msg_generator)} messages in {file_path}")
        for i, msg in enumerate(msg_generator):
            try:
                out = {
                    **EmlParser.parse_meta(msg=msg, return_raw_header=return_raw_header),
                    **EmlParser.parse_parts(msg=msg, extract_children=extract_children, out_dir=out_dir),
                }
                yield out
            except Exception as e:
                logger.error(f"Error parsing message {i}: {e}")
                continue
