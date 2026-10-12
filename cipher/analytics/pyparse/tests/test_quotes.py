from datetime import datetime

import pytest
from pyparse.parsers.email.quotes import find_quoted_blocks

from cipher.schemas.content.email import QuoteKind


def _quoted(text: str, block) -> str:
    return text[block.start_offset : block.end_offset]


@pytest.mark.parametrize(
    ("attribution", "name", "address"),
    [
        ("On Mon, Jul 21, 2025 at 7:28 AM Megan Flick <megan@x.com> wrote:", "Megan Flick", "megan@x.com"),
        ("On Jul 21, 2025, at 7:28 AM, Megan Flick <megan@x.com> wrote:", "Megan Flick", "megan@x.com"),
        ("Le lun. 21 juil. 2025 à 07:28, Megan Flick <megan@x.com> a écrit :", "Megan Flick", "megan@x.com"),
        ("El lun, 21 jul 2025 a las 7:28, Megan Flick (<megan@x.com>) escribió:", "Megan Flick", "megan@x.com"),
        ("Am Mo., 21. Juli 2025 um 07:28 Uhr schrieb Megan Flick <megan@x.com>:", "Megan Flick", "megan@x.com"),
        ("пн, 21 июл. 2025 г. в 07:28, Megan Flick <megan@x.com>:", "Megan Flick", "megan@x.com"),
        ("21.07.2025 7:28, Мегана Флик пишет:", "Мегана Флик", None),
        ("在 2025年7月21日周一 07:28，Megan Flick <megan@x.com> 写道：", "Megan Flick", "megan@x.com"),
        ("‏في الاثنين، 21 يوليو 2025 في 7:28 ص كتب Megan Flick <‎megan@x.com‎>:‏", "Megan Flick", "megan@x.com"),
    ],
)
def test_reply_attributions_in_many_languages(attribution: str, name: str, address: str | None):
    """Each client/language attribution opens a reply block running to the end, with its author."""
    text = f"Sounds good, see you then.\n\n{attribution}\n\nCan we meet Tuesday?\n"
    [block] = find_quoted_blocks(text)
    assert block.kind == QuoteKind.REPLY
    assert _quoted(text, block) == f"{attribution}\n\nCan we meet Tuesday?"
    assert (block.from_name, block.from_address) == (name, address)


def test_wrapped_plain_text_attribution():
    """Plain-text clients wrap a long attribution over two lines."""
    text = "Fine.\n\nOn Mon, Jul 21, 2025 at 7:28 AM Megan Flick <\nmegan@x.com> wrote:\n> Can we meet?\n"
    [block] = find_quoted_blocks(text)
    assert block.attribution.startswith("On Mon") and block.from_address == "megan@x.com"
    assert block.date_sent == datetime(2025, 7, 21, 7, 28)


def test_reply_history_splits_into_one_block_per_message():
    """A thread's quoted history is a block per earlier message, newest first."""
    text = (
        "Third.\n\nOn Tue, Jul 22, 2025 at 9:00 AM Bob <bob@y.com> wrote:\nSecond.\n\n"
        "On Mon, Jul 21, 2025 at 7:28 AM Megan <megan@x.com> wrote:\nFirst.\n"
    )
    first, second = find_quoted_blocks(text)
    assert _quoted(text, first).endswith("Second.") and first.from_address == "bob@y.com"
    assert _quoted(text, second).endswith("First.") and second.from_address == "megan@x.com"


def test_outlook_original_message_and_header_blocks():
    """Outlook's separator + header block, its separator-less form, and localized labels."""
    text = (
        "Thanks!\n\n-----Original Message-----\nFrom: Megan Flick [mailto:megan@x.com]\n"
        "Sent: Monday, July 21, 2025 7:28 AM\nTo: Nick\nSubject: lease\n\nKeep the lease?\n\n"
        "От: Иван Петров <ivan@y.ru>\nОтправлено: 20 июля 2025 г. 10:00\nКому: Megan\nТема: аренда\n\nПривет\n"
    )
    english, russian = find_quoted_blocks(text)
    assert english.kind == QuoteKind.REPLY and english.from_name == "Megan Flick"
    assert english.date_sent == datetime(2025, 7, 21, 7, 28)
    assert _quoted(text, english).endswith("Keep the lease?")
    assert (russian.from_name, russian.from_address, russian.date_sent) == ("Иван Петров", "ivan@y.ru", None)
    assert _quoted(text, russian).endswith("Привет")


@pytest.mark.parametrize(
    "intro",
    [
        "---------- Forwarded message ---------",
        "---------- Пересылаемое сообщение ----------",
        "-------- Message transféré --------",
        "Begin forwarded message:",
    ],
)
def test_forwards(intro: str):
    """Gmail/Thunderbird/Apple forwards in several languages are forward blocks with the original sender."""
    text = f"FYI\n\n{intro}\nFrom: Megan Flick <megan@x.com>\nDate: Mon, Jul 21, 2025 at 7:28 AM\nSubject: lease\nTo: Nick\n\nBody\n"
    [block] = find_quoted_blocks(text)
    assert block.kind == QuoteKind.FORWARD and block.from_address == "megan@x.com"
    assert _quoted(text, block).startswith(intro) and _quoted(text, block).endswith("Body")


def test_bottom_posted_reply_ends_with_its_quote():
    """When the writer answers below the `>` quote, their text is not part of the block."""
    text = "On Mon, Jul 21, 2025 at 7:28 AM Megan <megan@x.com> wrote:\n> Can we meet?\n>\n> Tuesday?\n\nYes, Tuesday works.\n"
    [block] = find_quoted_blocks(text)
    assert _quoted(text, block).endswith("> Tuesday?")


def test_interleaved_angle_quotes_without_attribution():
    """Bare `>` runs (inline replies) are reply blocks of their own."""
    text = "> point one\n> more\nagreed\n> point two\n> more\nno\n"
    blocks = find_quoted_blocks(text)
    assert [_quoted(text, block) for block in blocks] == ["> point one\n> more", "> point two\n> more"]


@pytest.mark.parametrize(
    "text",
    [
        "In 2019 John wrote: the report was late.\n",
        "Here is what she wrote:\nhello\n",
        "From: the desk of the editor\nwe have news\n",
        "Meeting at 10:30 tomorrow.\n",
    ],
)
def test_ordinary_prose_is_not_a_quote(text: str):
    """Prose that says "wrote:" or "From:" without a date/address/header block stays body text."""
    assert find_quoted_blocks(text) == []


def test_outlook_html_header_lines_in_separate_paragraphs():
    """HTML Outlook replies put blank lines between header lines, and wrap a long From onto `[mailto:]`."""
    text = "ok\n\nFrom: Nick Bolton\n[mailto:nick@x.com]\n\nSent: Tuesday, April 07, 2009 11:10 AM\n\nTo: Ed\n\nSubject: Fw: visit\n\nbody\n"
    [block] = find_quoted_blocks(text)
    assert (block.kind, block.from_name, block.from_address) == (QuoteKind.FORWARD, "Nick Bolton", "nick@x.com")
    assert block.date_sent == datetime(2009, 4, 7, 11, 10)


@pytest.mark.parametrize("text", ["Upgrade:\n>= 6.0.0\n\n< 13.1.2\n", "> Register\n\nThen head to the DAC\n"])
def test_version_ranges_and_lone_arrows_are_not_quotes(text: str):
    """`>= 6.0.0` dependency ranges and a single `> Register` arrow are not quotes."""
    assert find_quoted_blocks(text) == []
