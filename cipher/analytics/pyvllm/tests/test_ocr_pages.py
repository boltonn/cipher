from io import BytesIO

import pypdfium2 as pdfium
from PIL import Image
from pyvllm.ocr.pages import page_count, render_pages, scanned_pages


def _image_page_pdf() -> bytes:
    pdf = pdfium.PdfDocument.new()
    image = pdfium.PdfImage.new(pdf)
    image.set_bitmap(pdfium.PdfBitmap.from_pil(Image.new("RGB", (400, 500), "white")))
    image.set_matrix(pdfium.PdfMatrix().scale(612, 792))
    page = pdf.new_page(612, 792)
    page.insert_obj(image)
    page.gen_content()
    pdf.new_page(612, 792)
    buffer = BytesIO()
    pdf.save(buffer)
    return buffer.getvalue()


def test_pdf_pages_without_text_layer_are_scanned():
    data = _image_page_pdf()
    assert page_count(data) == 2
    assert scanned_pages(data) == [1, 2]


def test_render_respects_page_selection_and_max_side():
    rendered = list(render_pages(_image_page_pdf(), pages=[2], max_side=800))
    assert [number for number, _ in rendered] == [2]
    assert max(rendered[0][1].size) == 800


def test_multipage_tiff_frames_are_pages():
    buffer = BytesIO()
    frames = [Image.new("RGB", (3000, 1000), "white"), Image.new("RGB", (100, 100), "black")]
    frames[0].save(buffer, format="TIFF", save_all=True, append_images=frames[1:])
    data = buffer.getvalue()
    assert scanned_pages(data) == [1, 2]
    (number, image), _ = list(render_pages(data, max_side=1600))
    assert number == 1 and image.size == (1600, 533)
