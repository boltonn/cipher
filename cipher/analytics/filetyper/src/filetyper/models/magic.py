import json
import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from loguru import logger

from filetyper.schemas import FileTypeInfo

DEFAULT_REGISTRY_PATH = Path(__file__).parent.parent / "data" / "registry.json"

# OOXML formats are themselves zip archives, so they match the generic zip
# magic number; these internal paths disambiguate them from a plain zip.
_OOXML_ZIP_MARKERS = {
    "word/document.xml": "docx",
    "xl/workbook.xml": "xlsx",
    "ppt/presentation.xml": "pptx",
}

# An mbox opens with its first message's `From <sender> <asctime>` separator line (an .eml never does).
MBOX_FROM_LINE = re.compile(
    rb"From \S+ +(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) +(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
)


class MagicNumberFilterTyper:
    def __init__(self, registry_path: Path | None = None):
        registry_path = registry_path or DEFAULT_REGISTRY_PATH
        with registry_path.open("r") as f:
            full_registry = json.load(f)

        # 1. Pre-compile Magic Bytes
        self._magic_rules = [
            {
                "magic": (
                    item["magic"].encode()
                    if isinstance(item["magic"], str)
                    else bytes(item["magic"])  # list of ints to bytes
                ),
                "offset": item.get("offset", 0),
                "info": self._build_info(item),
            }
            for item in full_registry
            if item.get("magic")
        ]

        # 2. Pre-map Extensions for O(1) lookup
        # We flatten the list of extensions so each one is a key
        self._extension_map = {
            ext.lower(): self._build_info(item) for item in full_registry for ext in (item.get("extensions") or [])
        }

        self._name_map = {item["name"]: self._build_info(item) for item in full_registry}

        # 3. Pre-map MIME types
        self._mime_type_map = {
            item["mime_type"]: self._build_info(item) for item in full_registry if item.get("mime_type")
        }

    @property
    def max_magic_length(self) -> int:
        """Calculate the maximum length of magic signatures for efficient reading."""
        if not self._magic_rules:
            return 0
        return max(len(rule["magic"]) + rule["offset"] for rule in self._magic_rules)

    def _build_info(self, item: dict) -> FileTypeInfo:
        """Helper to create the TypedDict."""
        return FileTypeInfo(
            filetype=item["name"],
            filetype_group=item["group"],
            mime_type=item["mime_type"],
            extensions=item.get("extensions"),
        )

    def infer_bytes(self, data: bytes) -> FileTypeInfo | None:
        """Infer file type from raw bytes using magic numbers (no bytes at all: `empty`)."""
        if not data:
            return self._name_map.get("empty")
        for rule in self._magic_rules:
            magic = rule["magic"]
            offset = rule["offset"]

            # Match-case is still fine, but a simple slice comparison is very fast
            if data[offset : offset + len(magic)] == magic:
                if rule["info"]["filetype"] == "zip" and (ooxml_info := self._disambiguate_ooxml(BytesIO(data))):
                    return ooxml_info
                return rule["info"]
        if MBOX_FROM_LINE.match(data):
            return self._name_map.get("mbox")
        return None

    def infer_path(self, path: Path, n: int | None = None, name: str | None = None) -> FileTypeInfo | None:
        """Infer type from magic bytes, then the extension of `name` (default: the path's own name).

        Pass `name` when the bytes live somewhere their name doesn't (a blob named by its hash).
        """
        n = n or self.max_magic_length
        try:
            if path.stat().st_size == 0:
                return self._name_map.get("empty")
            with path.open("rb") as f:
                header = f.read(n)
                if info := self.infer_bytes(header):
                    if info["filetype"] == "zip" and (ooxml_info := self._disambiguate_ooxml(path)):
                        return ooxml_info
                    return info
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not read file at {path} for byte inference: {e}")

        # 2. Try Extension Matching (Fallback)
        # O(1) lookup in our pre-compiled map
        # logger.debug(f"Falling back to extension matching for {path.name}")
        return self.match_extension(Path(name or path.name).suffix)

    def _disambiguate_ooxml(self, file: Path | BinaryIO) -> FileTypeInfo | None:
        """Peek at a zip-matched file's internal listing to tell docx/xlsx/pptx apart from a plain zip.

        A header-only prefix (no central directory) can't be told apart and returns None.
        """
        try:
            with zipfile.ZipFile(file) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return None

        for marker, filetype in _OOXML_ZIP_MARKERS.items():
            if marker in names:
                return self._extension_map.get(filetype)
        return None

    def infer_stream(self, stream: BinaryIO) -> FileTypeInfo | None:
        """Infer type from a seekable binary stream without reading everything."""
        # 1. Peek only what we need for the longest magic number
        n = self.max_magic_length
        if n == 0:
            return None

        current_pos = stream.tell()
        header = stream.read(n)
        stream.seek(current_pos)  # Reset for the next consumer

        return self.infer_bytes(header)

    def match_extension(self, ext: str) -> FileTypeInfo | None:
        """Helper to match file extension using the pre-compiled map."""
        ext = ext.lower().lstrip(".")
        return self._extension_map.get(ext)

    def get_filetype_info(self, filetype: str) -> FileTypeInfo | None:
        """The registry entry for a filetype name (e.g. `wmv`), or None if it isn't registered."""
        return self._name_map.get(filetype)

    def map_mime_type_to_filetype_info(self, mime_type: str) -> FileTypeInfo:
        """Same interface as Magika wrapper."""
        return self._mime_type_map.get(
            mime_type,
            FileTypeInfo(
                filetype="unknown",
                filetype_group="unknown",
                mime_type=mime_type,
                extensions=None,
            ),
        )
