"""AI/ML based file typing.

Specifically using Google's Magika. This was chosen
so that we can fine-tune ONNX models if needed.
"""

import json
from pathlib import Path
from typing import BinaryIO

from loguru import logger
from magika import Magika

from filetyper.schemas import FileTypeInfo


class MagikaFileTyper:
    """A thin wrapper around Magika to infer file types.

    Use it to conform to the expected interface for file typers in Cipher.
    And to return Cipher's File schema. And to use utility methods if needed.
    """

    def __init__(self):
        self._model = Magika()
        self._mime_type_map = self._get_mime_type_to_filetype_info_map()

    def export_filetype_info(self, path: Path) -> None:
        """Export a mapping of filetype descriptions."""
        registry_data = sorted(
            [
                {
                    "name": info.label,
                    "group": info.group,
                    "mime_type": info.mime_type,
                    "extensions": info.extensions,
                }
                for info in self._model._cts_infos.values()
            ],
            key=lambda x: x["name"],
        )

        with path.open("w") as f:
            json.dump(registry_data, f, indent=4)

        logger.success(f"Successfully exported {len(registry_data)} types to {path}")

    def _get_mime_type_to_filetype_info_map(self) -> dict[str, FileTypeInfo]:
        """Get a mapping of mime types to file type information."""
        return {
            info.mime_type: FileTypeInfo(
                filetype_group=info.group,
                filetype=info.label,
                mime_type=info.mime_type,
                extensions=info.extensions,
            )
            for info in self._model._cts_infos.values()
            if info.mime_type
        }

    def infer_path(self, path: Path) -> FileTypeInfo:
        """Infer the file type information from a file path."""
        info = self._model.identify_path(path)
        return FileTypeInfo(
            filetype_group=info.output.group,
            filetype=info.output.label,
            mime_type=info.output.mime_type,
            extensions=info.output.extensions,
        )

    def infer_bytes(self, data: bytes) -> FileTypeInfo:
        """Best for small blobs already in memory."""
        info = self._model.identify_bytes(data)
        return FileTypeInfo(
            filetype_group=info.output.group,
            filetype=info.output.label,
            mime_type=info.output.mime_type,
            extensions=None,
        )

    def infer_stream(self, stream: BinaryIO) -> FileTypeInfo:
        """Infer file type from a stream. Magika can read from file-like objects."""
        info = self._model.identify_stream(stream)
        return FileTypeInfo(
            filetype_group=info.output.group,
            filetype=info.output.label,
            mime_type=info.output.mime_type,
            extensions=None,
        )

    def map_mime_type_to_filetype_info(
        self,
        mime_type: str,
    ) -> FileTypeInfo:
        """Map a mime type to FileTypeInfo."""
        info = self._mime_type_map.get(mime_type, None)
        if info is None:
            logger.warning(f"Mime type {mime_type} not found in Magika knowledge base.")
            return FileTypeInfo(
                filetype_group="unknown",
                filetype="unknown",
                mime_type=mime_type,
                extensions=None,
            )
        return info


if __name__ == "__main__":
    from rich.pretty import pprint

    model = MagikaFileTyper()
    path = Path(__file__)
    info = model.infer_path(path)
    pprint(info)
