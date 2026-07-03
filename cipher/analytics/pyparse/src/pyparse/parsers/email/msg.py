import email
from pathlib import Path

import compressed_rtf
from loguru import logger
from msg_parser.msg_parser import Message
from olefile import OleFileIO

from pyparse.parsers.base import get_file_instance
from pyparse.parsers.email.eml import EmlParser
from pyparse.parsers.text import HtmlParser
from pyparse.utils.text import clean_text


class MsgParser:
    @staticmethod
    def load_from_filesystem(file_path: Path) -> dict:
        """Load a msg file from the filesystem."""
        with OleFileIO(file_path) as ole:
            return MsgParser.create_msg(ole)

    @staticmethod
    def load_from_bytes(file_bytes: bytes) -> dict:
        """Load a msg file from bytes."""
        return MsgParser.create_msg(OleFileIO(file_bytes))

    @staticmethod
    def create_msg(ole: OleFileIO) -> dict:
        """Create a msg file from an OleFileIO object."""
        return Message(ole.root.kids_dict)

    @staticmethod
    def extract_attachments(
        msg: Message, extract_children: bool = False, out_dir: Path = None, **kwargs
    ) -> dict:
        """Extract data from a msg file."""
        attachements = []
        for attachment in msg.attachments.values():
            attachment_bytes = attachment.get("AttachDataObj")
            file_ext = attachment.get("AttachExtension")
            file_name = attachment.get("DisplayName")
            meta = {
                "file_name": file_name,
                "file_extension": file_ext,
                **get_file_instance(attachment_bytes),
            }
            if extract_children:
                out_file_ext = ".bin" if file_ext is None else file_ext
                out_file_name = meta["hash"]["md5"] + out_file_ext
                out_file = out_dir / out_file_name
                with open(out_file, "wb") as fb:
                    fb.write(attachment_bytes)
                meta["path"] = out_file
                logger.debug(f"Extracted {out_file}")
            attachements.append(meta)
        return attachements if attachements else None

    @staticmethod
    def parse_properties(
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

        subject = meta.get("subject")
        out["subject"] = msg.properties.get("Subject") if subject is None else subject

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

    @staticmethod
    def parse(
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

        out = MsgParser.parse_properties(msg, return_raw_header=return_raw_header)
        out["children"] = MsgParser.extract_attachments(
            msg=msg, extract_children=extract_children, out_dir=out_dir
        )
        return out
