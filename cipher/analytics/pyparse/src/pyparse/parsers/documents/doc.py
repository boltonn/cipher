import tempfile
from pathlib import Path

from pyparse.parsers.documents.docx import DocxParser
from pyparse.utils.libreoffice import convert_with_libre


class DocParser:
    """Parse a doc file by converting it to docx and then using the docx parser.

    Supported formats: doc, docm, dot, dotm, odt, rtf
    """

    @staticmethod
    def parse(
        file: Path | bytes,
        encoding: str = None,
        extract_children: bool = False,
        out_dir: Path = None,
        append_comments: bool = True,
        delimiter: str = " ",
        page_delimiter: str = "",
        **kwargs,
    ) -> dict:
        """Parse a doc file."""
        if isinstance(file, (Path, str)):
            file_path = Path(file)

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = convert_with_libre(
                    file_path=file_path,
                    tmp_dir=tmp_dir,
                    target_format="docx",
                )

                return DocxParser.parse(
                    file=tmp_path,
                    encoding=encoding,
                    extract_children=extract_children,
                    out_dir=out_dir,
                    append_comments=append_comments,
                    delimiter=delimiter,
                    page_delimiter=page_delimiter,
                    **kwargs,
                )

        elif isinstance(file, bytes):
            with tempfile.NamedTemporaryFile(suffix=".doc") as tmp_file:
                tmp_file.write(file)
                return DocParser.parse(
                    file=tmp_file.name,
                    encoding=encoding,
                    extract_children=extract_children,
                    out_dir=out_dir,
                    append_comments=append_comments,
                    delimiter=delimiter,
                    page_delimiter=page_delimiter,
                    **kwargs,
                )
