from pyparse.parsers.text.html import HtmlParser


def test_blocks_inside_table_cells_stay_separated():
    """Layout-table emails: a cell's blocks must not glue into `Nick BoltonConfirmation`."""
    html = (
        "<div><table><tr><td><h1>Here is your invoice</h1><p>Hey Nick Bolton,</p><p>Thank you.</p>"
        "<div>Name: Nick Bolton</div><div>Confirmation #: 9947</div>Afghania<br>2311 M Street</td></tr></table></div>"
    )
    assert HtmlParser.to_text(html) == (
        "Here is your invoice\nHey Nick Bolton,\nThank you.\nName: Nick Bolton\nConfirmation #: 9947\nAfghania\n2311 M Street"
    )


def test_blocks_outside_tables_break_lines():
    """Block boundaries outside tables become newlines."""
    assert HtmlParser.to_text("<div>Nick Bolton</div><div>2311 Foo</div>") == "Nick Bolton\n2311 Foo"


def test_inline_content_running_into_a_block_breaks():
    """A block opening straight after inline text or an inline element starts a new line."""
    assert (
        HtmlParser.to_text("<div>Linear Algebra<div>Imperial College</div></div>") == "Linear Algebra\nImperial College"
    )
    assert HtmlParser.to_text("<div><b>Algorithms</b><div>Stanford</div></div>") == "Algorithms\nStanford"
    assert HtmlParser.to_text("<div><p>one</p><p>two</p></div>") == "one\ntwo"


def test_nested_layout_tables_emit_text_once():
    """Layout tables are unwrapped; only a leaf table with 2+ columns renders as a pipe table."""
    html = (
        "<div><table><tr><td><table><tr><td>Party of 2 for Nick Bolton</td></tr></table>"
        "<table><tr><th>Item</th><th>Price</th></tr><tr><td>Poke</td><td>$12</td></tr></table></td></tr></table></div>"
    )
    text = HtmlParser.to_text(html)
    assert text.count("Party of 2 for Nick Bolton") == 1
    assert text == "Party of 2 for Nick Bolton\n\n| Item | Price |\n|---|---|\n| Poke | $12 |"


def test_descriptive_alt_text_is_kept():
    """Image-only emails keep their message; icon alts are dropped."""
    html = '<div><img alt="Facebook"><img alt="Half off all poke bowls this Friday"></div>'
    assert HtmlParser.to_text(html) == "Half off all poke bowls this Friday"


def test_adjacent_links_get_a_space():
    """Links flush against another element are separated; a link inside a word is not."""
    assert (
        HtmlParser.to_text("<p><a>Ada Lovelace</a><span>in</span><a>Towards Data</a></p>")
        == "Ada Lovelace in Towards Data"
    )
    assert HtmlParser.to_text("<p>re<a>link</a>ed</p>") == "relinked"


def test_invisible_padding_is_stripped():
    """Preheader padding goes; a zero-width non-joiner inside a Persian word stays."""
    assert (
        HtmlParser.to_text("<p>Sale ends\u200c\u00a0\u200c\u00a0\u034f \u00ad\u2007tonight</p>") == "Sale ends tonight"
    )
    assert HtmlParser.to_text("<p>می\u200cخواهم</p>") == "می\u200cخواهم"


def test_control_bytes_are_dropped():
    """Corrupt trailing binary after a body must not make lxml refuse the text rewrite."""
    assert HtmlParser.to_text("<div><p>Hello</p></div>\x05\x12\x0f<p>tail</p>") == "Hello\n\ntail"
