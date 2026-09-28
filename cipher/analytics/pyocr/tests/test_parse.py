from pyocr.parse import parse_page

# Shapes observed from jina-ocr-v1 on real pages.
TABLE_OUTPUT = """## Release History:

<table>
<thead>
  <tr><th>v4.2.0</th><th>1. First release.</th></tr>
  <tr><th>v4.3.2</th><th>1. To fix p2p issues<br>2. To improve throughput</th></tr>
</thead>
</table>

Done."""

FIGURE_OUTPUT = """Annual Logistics Summary

<|ref|>Bar chart showing shipments by quarter<|/ref|><|det|>[[246,160,750,400]]<|/det|>

Volumes peaked in Q4."""


def test_html_table_becomes_extracted_table_and_pipe_markdown():
    page = parse_page(TABLE_OUTPUT, page_number=2)
    assert page.tables[0].cells == [
        ["v4.2.0", "1. First release."],
        ["v4.3.2", "1. To fix p2p issues 2. To improve throughput"],
    ]
    assert page.tables[0].page_number == 2
    assert "<table" not in page.markdown
    assert "| v4.2.0 | 1. First release. |" in page.markdown
    assert page.markdown.endswith("Done.")


def test_spans_are_expanded():
    page = parse_page(
        '<table><tr><td colspan="2">A</td></tr><tr><td rowspan="2">B</td><td>1</td></tr><tr><td>2</td></tr></table>',
        page_number=1,
    )
    assert page.tables[0].cells == [["A", ""], ["B", "1"], ["B", "2"]]


def test_figure_becomes_region_and_caption_stays_out_of_text():
    page = parse_page(FIGURE_OUTPUT, page_number=1)
    assert page.markdown == "Annual Logistics Summary\n\nVolumes peaked in Q4."
    (region,) = page.regions
    assert region.text == "Bar chart showing shipments by quarter"
    assert round(region.bounding_box.xmin, 3) == round(246 / 999, 3)
    assert round(region.bounding_box.ymax, 3) == round(400 / 999, 3)


def test_markdown_image_figure_form():
    page = parse_page("Intro\n\n![A map](images/10_20_300_400.png)\n\nEnd", page_number=1)
    assert page.markdown == "Intro\n\nEnd"
    assert page.regions[0].text == "A map"


def test_null_output_is_empty_page():
    assert parse_page("null", page_number=3).markdown == ""
    assert parse_page("  ", page_number=3).markdown == ""


def test_unlocated_image_placeholder_and_special_tokens_are_dropped():
    page = parse_page("Contact: J. Alvarez\n\n![image](image_placeholder)<｜end▁of▁sentence｜>", page_number=1)
    assert page.markdown == "Contact: J. Alvarez"
    assert page.regions == []
