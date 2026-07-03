import tempfile
from pathlib import Path

from pyparse.parsers.documents.pptx import PptxParser
from pyparse.utils.libreoffice import convert_with_libre


class PptParser:
    """Generic parser for older PowerPoint files.

    Supported formats: ppt, pos, pptm, key/kth, odp
    """

    @staticmethod
    def parse(
        file: Path | bytes,
        extract_children: bool = False,
        out_dir: Path = None,
        **kwargs,
    ):
        """Parse a powerpoint file."""
        if isinstance(file, (Path, str)):
            file_path = Path(file)

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = convert_with_libre(
                    file_path=file_path,
                    tmp_dir=tmp_dir,
                    target_format="pptx",
                )

                return PptxParser.parse(
                    file=tmp_path,
                    extract_children=extract_children,
                    out_dir=out_dir,
                    **kwargs,
                )

        elif isinstance(file, bytes):
            with tempfile.NamedTemporaryFile(suffix=".ppt") as tmp_file:
                tmp_file.write(file)
                return PptParser.parse(
                    file=tmp_file.name,
                    extract_children=extract_children,
                    out_dir=out_dir,
                    **kwargs,
                )
