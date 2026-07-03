import io
import quopri
import re
from collections import defaultdict
from collections.abc import Generator
from pathlib import Path
from typing import Any, BinaryIO

from dateutil import parser as date_parser
from dateutil.parser import ParserError
from loguru import logger

from pyparse.utils.mobile import normalize_phone_number
from cipher.schemas import Contact


class VcardParser:
    """Parser for vCard / VCF files (RFC 6350) using streaming generators."""

    @staticmethod
    def _decode_value(value: str, params: dict[str, str]) -> str:
        """Handles Quoted-Printable and Charset decoding for 'weird' values."""
        encoding = params.get("ENCODING", "").upper()
        charset = params.get("CHARSET", "UTF-8").upper()

        if encoding in ("QUOTED-PRINTABLE", "QP"):
            try:
                byte_val = value.encode(charset, errors="ignore")
                decoded_bytes = quopri.decodestring(byte_val)
                return decoded_bytes.decode(charset, errors="ignore")
            except Exception as e:
                logger.warning(f"Failed to decode Quoted-Printable value: {e}")
                return value
        return value

    @staticmethod
    def _unfold_stream(stream: io.TextIOWrapper) -> Generator[str, None, None]:
        buffer = ""
        for line in stream:
            if not line:
                continue
            if line[0] in " \t":
                buffer += line[1:].rstrip("\r\n")
            else:
                if buffer:
                    yield buffer
                buffer = line.rstrip("\r\n")
        if buffer:
            yield buffer

    @staticmethod
    def _parse_line(line: str) -> tuple[str, dict[str, str], str]:
        match = re.match(
            r"(?:(?P<group>[^.]+)\.)?(?P<name>[^;:]+)(?P<params>;[^:]*)?:(?P<value>.*)",
            line,
        )
        if not match:
            return None, {}, None

        name = match.group("name").upper()
        value = match.group("value").strip()
        params = {
            k.upper(): v
            for p in (
                match.group("params")[1:].split(";") if match.group("params") else []
            )
            if "=" in p and (parts := p.split("=", 1))
            for k, v in [parts]
        }
        return name, params, value

    @staticmethod
    def _map_field(
        contact: defaultdict[str, Any],
        name: str,
        params: dict[str, str],
        value: str,
        include_extras: bool = True,
    ):
        """Internal logic to map VCF fields using defaultdict capabilities."""
        value = VcardParser._decode_value(value, params)
        match name:
            case "ADR":
                contact["address"] = value.replace(";", " ").strip()
            case "BDAY":
                # format like "--1231" means "unknown year, but December 31st"
                if value.startswith("--"):
                    logger.warning(f"Birthday with unknown year: {value}")
                    pass
                try:
                    contact["date_of_birth"] = date_parser.parse(
                        value, dayfirst=True, fuzzy=True
                    )
                except ParserError as e:
                    logger.warning(f"Failed to parse birthday: {e}")
            case "CATEGORIES":
                pass
                # contact["categories"] = [cat.strip() for cat in value.split(",")]
            case "EMAIL":
                contact["emails"].append(value)
            case "FN":
                contact["full_name"] = value
            case "N":
                parts = value.split(";")
                contact["last_name"] = parts[0] if len(parts) > 0 else None
                contact["first_name"] = parts[1] if len(parts) > 1 else None
            case "NOTE":
                contact["note"] = value
            case "ORG":
                contact["organization"] = value.replace(";", " ").strip()
            case "PHOTO":
                if value.startswith("http://") or value.startswith("https://"):
                    logger.info(f"Skipping remote photo URL for the contact: {value}")
                else:
                    logger.info("Embedded photo data found, skipping for now.")
            case "TEL":
                normalized_phone_number, phone_number_type = normalize_phone_number(
                    value
                )  # Just to validate and normalize, but we keep the original value
                label = params.get("TYPE", "voice").lower()
                contact["phone_numbers"].append(
                    {
                        "value": normalized_phone_number,
                        "label": label,
                        "type": phone_number_type,
                    }
                )
            case "VERSION" | "X-ABLABEL":
                pass
            case _:
                logger.warning(f"Unmapped VCF field: {name} with value: {value}")
                if include_extras:
                    contact["raw_header"][name] = value

    @classmethod
    def stream(
        cls, stream: BinaryIO, encoding: str = "utf-8"
    ) -> Generator[Contact, None, None]:
        """Stream contacts from a VCF file one at a time, yielding dictionaries."""
        text_stream = io.TextIOWrapper(
            stream, encoding=encoding, errors="ignore", newline=""
        )
        current_contact = None

        for line in cls._unfold_stream(text_stream):
            name, params, value = cls._parse_line(line)
            if not name:
                continue

            if name == "BEGIN" and value == "VCARD":
                # Initialize with factory functions for specific keys
                current_contact = defaultdict(lambda: None)
                current_contact.update(
                    {"emails": [], "phone_numbers": [], "urls": [], "raw_header": {}}
                )
                continue

            if name == "END" and value == "VCARD":
                if current_contact:
                    # Convert back to standard dict for clean output
                    yield Contact.model_validate(dict(current_contact))
                current_contact = None
                continue

            if current_contact is not None:
                cls._map_field(
                    current_contact, name, params, value, include_extras=False
                )

        text_stream.detach()

    @classmethod
    def parse(cls, file: bytes | Path, encoding: str = "utf-8") -> list[Contact]:
        """Get all contacts from a VCF file at once.

        Warning: This will load the entire file into memory, so it's not recommended for large files.
        """
        if isinstance(file, bytes):
            buffer = io.BytesIO(file)
            return [contact for contact in cls.stream(buffer, encoding)]
        with open(file, "rb") as f:
            return [contact for contact in cls.stream(f, encoding)]
