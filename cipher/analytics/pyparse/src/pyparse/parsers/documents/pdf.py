import re
from dataclasses import dataclass
from io import BufferedReader, BytesIO
from pathlib import Path

import dateutil.parser as date_parser
from loguru import logger
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTContainer, LTPage, LTText
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import resolve1
from pdfminer.pdfparser import PDFParser
from pdfminer.psparser import PSLiteral
from pdfminer.utils import PDFDocEncoding

from pyparse.utils.pdf import PDFImageHandler
from pyparse.utils.text import clean_text


@dataclass
class TextExtraction:
    """Text extraction from a PDF page."""

    text: str
    bbox: dict | None = None


class PdfParser:
    """Parser for PDF files."""

    @staticmethod
    def clean_date(date: str):
        """Clean a date string."""
        date = re.split(r"[\+\-]", date.replace("D:", "").strip())[0]
        return date_parser.parse(date)

    @staticmethod
    def concatenate_page():
        """Concatenate pages."""
        pass

    @staticmethod
    def decode_pdf_meta(value):
        """Decode a PDFDocEncoding value to Unicode; from pdfplumber."""
        if isinstance(value, bytes) and value.startswith(b"\xfe\xff"):
            return value[2:].decode("utf-16be", "ignore")
        else:
            ords = (ord(c) if isinstance(c, str) else c for c in value)
            return "".join(PDFDocEncoding[o] for o in ords)

    @staticmethod
    def get_metadata_from_buffer(
        buffer: BufferedReader | BytesIO, password: str = None
    ):
        """Get metadata from a PDF file buffer."""
        parser = PDFParser(buffer)
        document = PDFDocument(parser, password=password)
        metadata = {}
        for info in document.info:
            metadata |= info
        for k, v in metadata.items():
            if hasattr(v, "resolve"):
                v = v.resolve()

            if isinstance(v, list):
                metadata[k] = list(map(PdfParser.decode_pdf_meta, v))
            elif isinstance(v, PSLiteral):
                metadata[k] = PdfParser.decode_pdf_meta(v.name)
            elif isinstance(v, bool):
                metadata[k] = v
            else:
                metadata[k] = PdfParser.decode_pdf_meta(v)

        _ = metadata.pop("mime_type", None)
        metadata["num_pages"] = resolve1(document.catalog["Pages"])["Count"]

        return metadata

    @staticmethod
    def get_metadata(file: Path | BytesIO | BufferedReader, password: str = None):
        """Get metadata from a PDF file."""
        if isinstance(file, (str, Path)):
            with file.open("rb") as fb:
                return PdfParser.get_metadata_from_buffer(fb, password=password)
        elif isinstance(file, (BytesIO, BufferedReader)):
            return PdfParser.get_metadata_from_buffer(file, password=password)
        else:
            raise TypeError(f"Unsupported type: {type(file)}")

    @staticmethod
    def parse_child(
        child,
        page_height: float,
        page_width: float,
        delimiter: str = " ",
        return_boxes: bool = False,
        img_handler: PDFImageHandler = None,
        cleaned: bool = True,
        _children: list = None,
    ):
        """Parse a child from a PDF page. Designed to be recursive."""
        _children = [] if _children is None else _children
        if isinstance(child, LTText):
            output = PdfParser.parse_text(
                child,
                page_height,
                page_width,
                cleaned=cleaned,
                delimiter=delimiter,
                return_box=return_boxes,
            )
            if output and output.text:
                _children.append(output)
        # elif isinstance(child, LTImage):
        #     output = PdfParser.parse_img(child=child, img_handler=img_handler)
        #     if output:
        #         _children.append(output)
        elif isinstance(child, LTContainer):
            for c in child:
                PdfParser.parse_child(
                    c,
                    page_height,
                    page_width,
                    delimiter=delimiter,
                    return_boxes=return_boxes,
                    img_handler=img_handler,
                    cleaned=cleaned,
                    _children=_children,
                )
        else:
            pass

        return _children

    # @staticmethod
    # def parse_img(child: LTImage, img_handler: PDFImageHandler) -> Image:
    #     """Parse an image from a PDF page."""
    #     return img_handler.handle_image(child)

    @staticmethod
    def parse_text(
        child: LTText,
        page_height: float,
        page_width: float,
        return_box: bool = False,
    ) -> TextExtraction:
        """Parse text from a PDF page."""
        text = child.get_text()
        if text:
            text = clean_text(text, extra_whitespace=True, trailing_punctuation=True)

            extraction = {"text": text}
            if return_box and hasattr(child, "bbox"):
                x1, y1, x2, y2 = child.bbox
                extraction["bbox"] = {
                    "xmin": x1 / page_width,
                    "ymin": y1 / page_height,
                    "xmax": x2 / page_width,
                    "ymax": y2 / page_height,
                }
            return TextExtraction(**extraction)

    @staticmethod
    def parse_page(
        page: LTPage,
        delimiter: str = " ",
        return_boxes: bool = False,
        img_handler: PDFImageHandler = None,
        cleaned: bool = True,
    ) -> list[TextExtraction]:
        """Parse a PDF page."""
        page_height = page.height
        page_width = page.width

        children = []
        for child in page:
            children.extend(
                PdfParser.parse_child(
                    child=child,
                    page_height=page_height,
                    page_width=page_width,
                    delimiter=delimiter,
                    return_boxes=return_boxes,
                    img_handler=img_handler,
                    cleaned=cleaned,
                )
            )
        return children

    @staticmethod
    def parse(
        file: Path | bytes,
        cleaned: bool = True,
        delimiter: str = " ",
        extract_children: bool = False,
        max_pages: int = None,
        out_dir: Path = None,
        page_delimiter: str = "\n\n",
        page_numbers: list[int] = None,
        password: str = None,
        return_boxes: bool = False,
        **kwargs,
    ):
        """Parse a PDF file."""
        if isinstance(file, bytes):
            file = BytesIO(file)

        out = PdfParser.get_metadata(file, password=password)
        img_handler = PDFImageHandler(
            extract_children=extract_children, out_dir=out_dir
        )

        max_pages = 0 if max_pages is None else max_pages
        pages = extract_pages(
            file, maxpages=max_pages, page_numbers=page_numbers, password=password
        )
        pages = [
            PdfParser.parse_page(
                page=page,
                delimiter=delimiter,
                return_boxes=return_boxes,
                img_handler=img_handler,
                cleaned=cleaned,
            )
            for page in pages
        ]
        pages = [
            PdfParser.standardize_page(page=page, delimiter=delimiter) for page in pages
        ]
        out["text"] = {
            "source": page_delimiter.join(
                [page["text"] for page in pages if page["text"]]
            ).strip()
        }
        # children: list[Image] = [img for page in pages for img in page["images"] if img]
        # if children:
        #     out["children"] = children
        return out

    @staticmethod
    def standardize_meta(meta: dict) -> dict:
        """Standardize metadata."""
        meta = {k.lower(): v for k, v in meta.items()}
        date_created = meta.pop("CreationDate", None)
        date_created = PdfParser.clean_date(date_created) if date_created else None
        date_modified = meta.pop("ModDate", None)
        date_modified = PdfParser.clean_date(date_modified) if date_modified else None
        created_by = meta.pop("Author", None)

        return {k: v for k, v in meta.items() if v is not None} | {
            "created_by": created_by,
            "date_created": date_created,
            "date_modified": date_modified,
        }

    @staticmethod
    def standardize_page(page: list[TextExtraction], delimiter: str = "\n\n") -> dict:
        """Standardize a page."""
        text = ""
        images = []
        for item in page:
            if isinstance(item, TextExtraction):
                text = delimiter.join([text, item.text])
            # elif isinstance(item, Image):
            #     images.append(item)
            else:
                logger.warning(f"Unknown item type: {type(item)}")
        return {"text": text, "images": images}
