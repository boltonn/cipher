import email
import hashlib
from pathlib import Path

import compressed_rtf
from filetyper import FileTyper
from loguru import logger
from msg_parser.msg_parser import Message
from olefile import OleFileIO

from pyparse.parsers.email.eml import EmlParser
from pyparse.parsers.text import HtmlParser
from pyparse.utils.text import clean_text


class MsgParser:
    """Parser for Outlook .msg files.

    Takes the same `file_typer` dependency as `EmlParser` and for the same
    reason: attachment typing shouldn't trust a possibly-missing/wrong
    `AttachExtension` string from the OLE structure when a magic-byte-based
    inference is available and just as cheap to reuse across attachments.
    """

    def __init__(self, file_typer: FileTyper | None = None) -> None:
        self.file_typer = file_typer or FileTyper()

    @staticmethod
    def load_from_filesystem(file_path: Path) -> Message:
        """Load a msg file from the filesystem."""
        with OleFileIO(file_path) as ole:
            return MsgParser.create_msg(ole)

    @staticmethod
    def load_from_bytes(file_bytes: bytes) -> Message:
        """Load a msg file from bytes."""
        return MsgParser.create_msg(OleFileIO(file_bytes))

    @staticmethod
    def create_msg(ole: OleFileIO) -> Message:
        """Create a msg file from an OleFileIO object."""
        return Message(ole.root.kids_dict)

    def extract_attachments(
        self, msg: Message, extract_children: bool = False, out_dir: Path = None, **kwargs
    ) -> dict:
        """Extract data from a msg file."""
        attachements = []
        for attachment in msg.attachments.values():
            attachment_bytes = attachment.get("AttachDataObj")
            file_name = attachment.get("DisplayName")
            filetype_info = self.file_typer.infer(attachment_bytes)
            md5 = hashlib.md5(attachment_bytes).hexdigest()
            sha256 = hashlib.sha256(attachment_bytes).hexdigest()
            meta = {
                "file_name": file_name,
                "filetype": filetype_info.get("filetype"),
                "filetype_group": filetype_info.get("filetype_group"),
                "mime_type": filetype_info.get("mime_type"),
                "md5": md5,
                "sha256": sha256,
            }
            if extract_children:
                ext = (filetype_info.get("extensions") or [None])[0]
                out_file_name = f"{md5}.{ext}" if ext else f"{md5}.bin"
                out_file = out_dir / out_file_name
                with open(out_file, "wb") as fb:
                    fb.write(attachment_bytes)
                meta["path"] = out_file
                logger.debug(f"Extracted {out_file}")
            attachements.append(meta)
        return attachements if attachements else None

    def parse_properties(
        self,
        msg: Message,
        return_raw_header: bool = True,
        body_delimiter: str = "\n\n",
    ) -> dict:
        """Parse a msg file."""
        out = {}
        header = msg.properties.get("TransportMessageHeaders")
        header = email.message_from_string(header)
        meta = EmlParser.parse_meta(header, return_raw_header=return_raw_header)

        date_sent = meta.pop("date_sent", None)
        date_sent = (
            msg.properties.get("DeliverTime") if date_sent is None else date_sent
        )
        if date_sent is not None:
            out["date_sent"] = EmlParser.parse_date(date_sent)

        subject = meta.get("title")
        out["title"] = msg.properties.get("Subject") if subject is None else subject

        sender = meta.get("sender")
        out["sender"] = (
            msg.properties.get("SenderRepresentingSmtpAddress")
            if sender is None
            else sender
        )

        message_id = meta.get("message_id")
        out["message_id"] = (
            msg.properties.get("InternetMessageId")
            if message_id is None
            else message_id
        )

        html_content = ""
        if "Html" in msg.properties:
            html_content = msg.properties.get("Html")
            html_content = HtmlParser.parse_str(html_content)

        plain_content = msg.properties.get("Body")
        if plain_content is not None:
            plain_content = clean_text(plain_content)
            if isinstance(plain_content, bytes):
                try:
                    plain_content = plain_content.decode("utf-8")
                except Exception as err:
                    logger.error(
                        f"Error decoding plain content likely b/c not base64: {err}"
                    )

        rtf_content = ""
        compressed_rtf_content = msg.properties.get("RtfCompressed")
        if compressed_rtf_content is not None:
            try:
                rtf_content = compressed_rtf.decompress(compressed_rtf_content)
            except Exception as err:
                logger.error(f"Error decompressing rtf content: {err}")

        text = body_delimiter.join([plain_content, html_content, rtf_content])
        text = clean_text(text, extra_whitespace=True, trailing_punctuation=True)
        if text:
            out["text"]["source"] = text
        return out

    def parse(
        self,
        file: Path | bytes,
        return_raw_header: bool = True,
        extract_children: bool = False,
        out_dir: Path = None,
    ):
        """Parse a msg file."""
        if isinstance(file, (str, Path)):
            msg = MsgParser.load_from_filesystem(Path(file))
        elif isinstance(file, bytes):
            msg = MsgParser.load_from_bytes(file)
        else:
            raise TypeError(f"Expected Path or bytes, got {type(file)}")

        out = self.parse_properties(msg, return_raw_header=return_raw_header)
        out["children"] = self.extract_attachments(
            msg=msg, extract_children=extract_children, out_dir=out_dir
        )
        return out
