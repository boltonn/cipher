import asyncio

import pytest
from PIL import Image, ImageDraw, ImageFont
from pyocr.schemas import OcrRequest

indra_ocr = pytest.importorskip("indra_ocr")
try:
    indra_ocr.model_dir()
except indra_ocr.ModelError:
    pytest.skip("Indra OCR models not downloaded (`make download-indra`)", allow_module_level=True)

from pyocr.indra import IndraOcr  # noqa: E402


def _page(path, lines: list[str]) -> None:
    image = Image.new("RGB", (1700, 2200), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    for index, line in enumerate(lines):
        draw.text((120, 150 + 70 * index), line, fill="black", font=font)
    image.save(path)


def test_reads_pages_in_process(tmp_path):
    pdf = tmp_path / "scan.pdf"
    first, second = tmp_path / "1.png", tmp_path / "2.png"
    _page(first, ["Quarterly report", "The meeting is on 12 March 2026."])
    _page(second, ["Second page", "Call Anna Lee on Friday."])
    Image.init()  # the PDF writer needs the JPEG plugin registered
    Image.open(first).save(pdf, save_all=True, append_images=[Image.open(second)])

    async def run():
        client = IndraOcr(workers=2)
        try:
            assert await client.health()
            every = await client.ocr(pdf, OcrRequest())
            picked = await client.ocr(pdf, OcrRequest(pages=[2]))
            none = await client.ocr(pdf, OcrRequest(pages=[]))
        finally:
            await client.aclose()
        return every, picked, none

    every, picked, none = asyncio.run(run())
    assert every.page_count == 2 and [page.page_number for page in every.pages] == [1, 2]
    assert "12 March 2026" in every.pages[0].markdown
    assert [page.page_number for page in picked.pages] == [2] and "Anna Lee" in picked.pages[0].markdown
    assert none.pages == []
