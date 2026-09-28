from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import dateutil.parser as date_parser
import docx
from bs4 import BeautifulSoup
from docx.enum.section import WD_SECTION_START
from docx.section import Section, _Footer, _Header
from docx.table import Table
from docx.text.pagebreak import RenderedPageBreak
from docx.text.paragraph import Paragraph

from pyparse.parsers.archives.zip import ZipParser
from pyparse.utils.msoffice import convert_table_to_text, parse_meta
from pyparse.utils.text import clean_text

# TODO: add support for links as annotations with selector urls


@dataclass
class Comment:
    """A comment on a docx file."""

    created_by: str = None
    date: datetime = None
    initials: str = None
    text: str = None


class DocxParser:
    @staticmethod
    def parse_comments(archive: ZipFile) -> list[Comment]:
        """Parse the comments from a docx file."""

        def _combine_name(comment: dict) -> str:
            """Combine the name of the comment."""
            initials = comment.pop("initials", None)
            created_by = comment.pop("created_by", None)
            if initials and created_by:
                return f"{created_by} ({initials})"
            elif initials:
                return initials
            elif created_by:
                return created_by
            else:
                return None

        try:
            comments = archive.read("word/comments.xml")
        except KeyError:
            return None
        soup = BeautifulSoup(comments, "xml")
        comments = [
            {
                "created_by": comment.get("w:author") if "w:author" in comment.attrs else None,
                "initials": comment.get("w:initials") if "w:initials" in comment.attrs else None,
                "date": date_parser.parse(comment.get("w:date")) if "w:date" in comment.attrs else None,
                "text": clean_text(comment.string),
            }
            for comment in soup.find_all("w:comment")
        ]
        return [Comment(**_combine_name(comment)) for comment in comments]

    @staticmethod
    def convert_comments_to_text(comments: list[Comment]) -> str:
        """Convert a list of comments to text."""
        return "\n".join(
            ["Comments:"] + [f"{c.created_by} @{c.date}: {c.text}" for c in comments if c.text is not None]
        )

    @staticmethod
    def parse_images(archive: ZipFile, extract: bool = False, out_dir: Path = None) -> list[dict]:
        """Parse the images from a docx file."""
        images = [i for i in archive.infolist() if not i.is_dir() and i.filename.startswith("word/media/")]
        return [
            ZipParser.extract(
                info=i,
                archive=archive,
                extract_children=extract,
                out_dir=out_dir,
            )
            for i in images
        ]

    @staticmethod
    def _iter_section_page_breaks(page_number: int, section_idx: int, section: Section) -> bool:
        """Generate zero-or-one `PageBreak` document elements for `section`.

        A docx section has a "start" type which can be "continuous" (no page-break), "nextPage",
        "evenPage", or "oddPage". For the next, even, and odd varieties, a `w:renderedPageBreak`
        element signals one page break. Here we only need to handle the case where we need to add
        another, for example to go from one odd page to another odd page and we need a total of
        two page-breaks.
        """
        to_iter = False

        def page_is_odd(page_number) -> bool:
            return page_number % 2 == 1

        start_type = section.start_type

        if start_type == WD_SECTION_START.EVEN_PAGE:  # noqa
            if not page_is_odd(page_number):
                to_iter = True

        elif start_type == WD_SECTION_START.ODD_PAGE:
            # the first page of the document is an implicit "new" odd-page, so no page-break --
            if section_idx == 0:
                pass
            if page_is_odd(page_number):
                to_iter = True

        # otherwise, start-type is one of "continuous", "new-column", or "next-page", none of
        # which need our help to get the page-breaks right.
        return to_iter

    @staticmethod
    def _iter_section_headers(section: Section, odd_and_even_pages_header_footer: bool) -> list[_Header]:
        """Iterate through the headers of a section."""
        headers = []

        def maybe_add_header(header: _Header):
            if header.is_linked_to_previous is False:
                return DocxParser.parse_header_footer_text(header)

        headers.append(maybe_add_header(section.header))
        if section.different_first_page_header_footer:
            headers.append(maybe_add_header(section.first_page_header))
        if odd_and_even_pages_header_footer:
            headers.append(maybe_add_header(section.even_page_header))
        return [header for header in headers if header is not None]

    @staticmethod
    def _iter_section_footers(section: Section, odd_and_even_pages_header_footer: bool) -> list[_Header]:
        """Iterate through the footers of a section."""
        footers = []

        def maybe_add_footer(footer: _Footer):
            if footer.is_linked_to_previous is False:
                return DocxParser.parse_header_footer_text(footer)

        footers.append(maybe_add_footer(section.footer))
        if section.different_first_page_header_footer:
            footers.append(maybe_add_footer(section.first_page_footer))
        if odd_and_even_pages_header_footer:
            footers.append(maybe_add_footer(section.even_page_footer))
        return [footer for footer in footers if footer is not None]

    @staticmethod
    def _iter_paragraph_items(
        paragraph: Paragraph,
    ) -> Iterator[Paragraph | RenderedPageBreak]:
        """Generate Paragraph and RenderedPageBreak items from `paragraph`.

        Each generated paragraph is the portion of the paragraph on the same page. When the
        paragraph contains no page-breaks, it is iterated unchanged and iteration stops. When
        there is a page-break, in general there one paragraph "fragment" before the page break,
        the page break, and then the fragment after the page break. However many combinations
        are possible. The first item can be either a page-break or a paragraph, but the type
        always alternates throughout the sequence.
        """
        if not paragraph.contains_page_break:
            yield paragraph
            return

        page_break = paragraph.rendered_page_breaks[0]

        # preceding-fragment is None when first paragraph content is a page-break
        preceding_paragraph_fragment = page_break.preceding_paragraph_fragment
        if preceding_paragraph_fragment:
            yield preceding_paragraph_fragment

        yield page_break

        # following-fragment is None when page-break is last paragraph content.
        # This is probably quite rare (Word moves these to the start of the next paragraph) but
        # easier to check for it than prove it can't happen.
        following_paragraph_fragment = page_break.following_paragraph_fragment
        # the paragraph fragment following a page-break can itself contain
        # another page-break. This would also be quite rare, but it can happen so we just
        # recurse into the second fragment the same way we handled the original paragraph.
        if following_paragraph_fragment:
            yield from DocxParser._iter_paragraph_items(following_paragraph_fragment)

    @staticmethod
    def parse_header_footer_text(hdrftr: _Header | _Footer) -> str:
        r"""The text enclosed in `hdrftr` as a single string.

        Each paragraph is included along with the text of each table cell. Empty text is omitted.
        Each paragraph text-item is separated by a newline ("\n") although note that a paragraph
        that contains a line-break will also include a newline representing that line-break, so
        newlines do not necessarily distinguish separate paragraphs.

        The entire text of a table is included as a single string with a space separating the text
        of each cell.

        A header with no text or only whitespace returns the empty string ("").
        """

        def iter_hdrftr_texts(hdrftr: _Header | _Footer) -> Iterator[str]:
            """Generate each text item in `hdrftr` stripped of leading and trailing whitespace.

            This includes paragraphs as well as table cell contents.
            """
            for block_item in hdrftr.iter_inner_content():
                if isinstance(block_item, Paragraph):
                    yield block_item.text.strip()
                elif isinstance(block_item, Table):
                    yield convert_table_to_text(block_item)
                else:
                    raise TypeError(f"Unexpected block item type: {type(block_item)}")

        return "\n".join(text for text in iter_hdrftr_texts(hdrftr) if text)

    @staticmethod
    def parse_section_text(
        doc: docx.document.Document,
        delimiter: str = " ",
        page_delimiter: str = "",
    ) -> str:
        """Parse the text from a docx file with sections."""
        odd_and_even_pages_header_footer = doc.settings.odd_and_even_pages_header_footer
        page_number = 0
        elements = []

        for section_idx, section in enumerate(doc.sections):
            to_iter = DocxParser._iter_section_page_breaks(
                page_number=section_idx,
                section_idx=section_idx,
                section=section,
            )
            if to_iter:
                page_number += 1
                elements.append(page_delimiter)
            elements.extend(
                DocxParser._iter_section_headers(
                    section,
                    odd_and_even_pages_header_footer=odd_and_even_pages_header_footer,
                )
            )

            for block_item in section.iter_inner_content():
                if isinstance(block_item, Paragraph):
                    for paragraph_item in DocxParser._iter_paragraph_items(block_item):
                        if isinstance(paragraph_item, Paragraph):
                            elements.append(paragraph_item.text)
                        elif isinstance(paragraph_item, RenderedPageBreak):
                            elements.append(page_delimiter)
                            page_number += 1

                elif isinstance(block_item, Table):
                    elements.append(convert_table_to_text(block_item))
                else:
                    raise TypeError(f"Unexpected block item type: {type(block_item)}")

            elements.extend(
                DocxParser._iter_section_footers(
                    section,
                    odd_and_even_pages_header_footer=odd_and_even_pages_header_footer,
                )
            )
        return delimiter.join(elements)

    @staticmethod
    def parse_sectionless_text(
        doc: docx.document.Document,
        delimiter: str = " ",
        page_delimiter: str = "",
    ) -> str:
        """Parse the text from a docx file without sections."""
        elements = []

        for block_item in doc.iter_inner_content():
            if isinstance(block_item, Paragraph):
                for paragraph_item in DocxParser._iter_paragraph_items(block_item):
                    if isinstance(paragraph_item, Paragraph):
                        elements.append(paragraph_item.text)
                    elif isinstance(paragraph_item, RenderedPageBreak):
                        elements.append(page_delimiter)

            elif isinstance(block_item, Table):
                elements.append(convert_table_to_text(block_item))
            else:
                raise TypeError(f"Unexpected block item type: {type(block_item)}")

        return delimiter.join(elements)

    @staticmethod
    def parse_text(
        doc: docx.document.Document,
        delimiter: str = " ",
        page_delimiter: str = "",
        cleaned: bool = True,
    ) -> str:
        """Parse the text from a docx file."""
        _fn = DocxParser.parse_section_text if len(doc.sections) > 0 else DocxParser.parse_sectionless_text
        text = _fn(
            doc=doc,
            delimiter=delimiter,
            page_delimiter=page_delimiter,
        )
        if cleaned:
            text = clean_text(text, extra_whitespace=True, trailing_punctuation=True)
        return text

    @staticmethod
    def parse(
        file: Path | bytes,
        extract_children: bool = False,
        out_dir: Path = None,
        delimiter: str = " ",
        page_delimiter: str = "",
        cleaned: bool = True,
        **kwargs,
    ) -> dict:
        """Parse a docx file."""
        if isinstance(file, bytes):
            file = BytesIO(file)
        elif isinstance(file, (Path, str)):
            file = Path(file)
        else:
            raise TypeError(f"Cannot parse {type(file)}")

        doc = docx.Document(file)
        out = parse_meta(doc=doc)

        text = DocxParser.parse_text(
            doc=doc,
            delimiter=delimiter,
            page_delimiter=page_delimiter,
            cleaned=cleaned,
        )

        archive = ZipFile(file)

        children: list[dict] = DocxParser.parse_images(archive=archive, extract=extract_children, out_dir=out_dir)
        if children:
            out["children"] = children

        # Note: archive extraction is better than docx package
        # TODO: have inline with the actual text preferred
        comments = DocxParser.parse_comments(archive=archive)
        if comments is not None:
            text += DocxParser.convert_comments_to_text(comments=comments)

        if text:
            out["text"] = {"source": text}

        return out
