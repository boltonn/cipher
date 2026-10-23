"""Turn a PDF or image into page images, and find which PDF pages actually need OCR."""

import re
import threading
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageSequence
from pillow_heif import register_heif_opener

register_heif_opener()

# The model tiles pages into <=9 640px crops, so rendering past ~2k px buys nothing.
DEFAULT_MAX_SIDE = 1600
# A page whose text layer has fewer word characters than this is treated as image-based.
DEFAULT_MIN_CHARS = 20

_WORD_CHAR_RE = re.compile(r"\w", re.UNICODE)
# pdfium is not thread-safe; page rendering runs in worker threads.
_PDFIUM_LOCK = threading.Lock()

Source = Path | bytes


def is_pdf(source: Source) -> bool:
    """Sniff the PDF magic bytes rather than trusting an extension.

    Like Acrobat and pdfium, the header may sit anywhere in the first 1024 bytes
    (e.g. a PDF saved with its HTTP response headers in front).
    """
    if isinstance(source, bytes):
        return b"%PDF-" in source[:1024]
    with open(source, "rb") as f:
        return b"%PDF-" in f.read(1024)


def _open_pdf(source: Source) -> pdfium.PdfDocument:
    return pdfium.PdfDocument(source if isinstance(source, bytes) else str(source))


def _open_image(source: Source) -> Image.Image:
    return Image.open(BytesIO(source) if isinstance(source, bytes) else source)


def _image_frames(image: Image.Image) -> list[Image.Image]:
    """Multi-page TIFFs are documents; every other raster (incl. animated GIF) is one page."""
    if image.format == "TIFF":
        return [frame.copy() for frame in ImageSequence.Iterator(image)]
    return [image]


def page_count(source: Source) -> int:
    """Number of pages (PDF) or frames (multi-page TIFF; 1 for other images)."""
    if is_pdf(source):
        with _PDFIUM_LOCK:
            pdf = _open_pdf(source)
            try:
                return len(pdf)
            finally:
                pdf.close()
    return len(_image_frames(_open_image(source)))


def scanned_pages(source: Source, min_chars: int = DEFAULT_MIN_CHARS) -> list[int]:
    """1-indexed PDF pages whose text layer is (near) empty -- the image-based ones worth OCR.

    Reading the text layer is milliseconds per page, so this runs before any
    rendering or model call. Non-PDF sources are all image, so every frame counts.
    """
    if not is_pdf(source):
        return list(range(1, page_count(source) + 1))
    pages = []
    with _PDFIUM_LOCK:
        pdf = _open_pdf(source)
        try:
            for index, page in enumerate(pdf, start=1):
                text = page.get_textpage().get_text_range()
                if len(_WORD_CHAR_RE.findall(text)) < min_chars:
                    pages.append(index)
        finally:
            pdf.close()
    return pages


def pages_to_read(source: Source, pages: list[int] | None, scanned_only: bool) -> tuple[int, list[int] | None]:
    """`(total pages, 1-indexed pages to OCR)`; None means every page."""
    total = page_count(source)
    if scanned_only:
        pages = [page for page in scanned_pages(source) if pages is None or page in pages]
    return total, pages


def _fit(image: Image.Image, max_side: int) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return image


def render_pages(
    source: Source, pages: list[int] | None = None, max_side: int = DEFAULT_MAX_SIDE
) -> Iterator[tuple[int, Image.Image]]:
    """Yield `(page_number, RGB image)` for the requested 1-indexed pages (all when None)."""
    wanted = set(pages) if pages else None
    if not is_pdf(source):
        for index, frame in enumerate(_image_frames(_open_image(source)), start=1):
            if wanted is None or index in wanted:
                yield index, _fit(frame, max_side)
        return

    # Lazily, one page at a time: a 300-page scan rendered up front is gigabytes.
    with _PDFIUM_LOCK:
        pdf = _open_pdf(source)
        total = len(pdf)
    try:
        for number in sorted(wanted) if wanted else range(1, total + 1):
            if not 1 <= number <= total:
                continue
            with _PDFIUM_LOCK:
                page = pdf[number - 1]
                width, height = page.get_size()
                image = page.render(scale=max_side / max(width, height)).to_pil().convert("RGB")
            yield number, image
    finally:
        with _PDFIUM_LOCK:
            pdf.close()
