from enum import StrEnum
from typing import TypedDict


class FileTypeInfo(TypedDict):
    filetype: str
    filetype_group: str
    mime_type: str | None
    extensions: list[str] | None


class FilteTyperStrategy(StrEnum):
    MAGIC_NUMBER = "magic_number"  # Use magic number signatures
    EXTENSION = "extension"  # Use file extension mapping
    MAGIKA = "magika"  # Use Magika's AI model
    DEFAULT = "default"  # Custom first, then Magika fallback (Default)
