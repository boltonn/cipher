import pytest

from cipher.datastores.postgres.utils import normalize_name, trim_name_span


@pytest.mark.parametrize(
    "variants",
    [
        ["Nick Bolton", "Nick Bolton's", "nick bolton’s", '"Nick Bolton"', "«Nick Bolton»", "'Nick Bolton'"],
        ["Roku, Inc.", "roku inc", "Roku Inc"],
        ["E. F. Bolton", "E.F. Bolton", "e f bolton", "EF Bolton"],
        ["O’Reilly", "O'Reilly", "O`Reilly"],
        ["Asia-Pacific", "Asia Pacific", "Asia–Pacific"],
        ["7-Eleven", "7‐Eleven"],
        ["Yahoo! Mail", "Yahoo Mail"],
        ["Indigo® Mastercard®", "Indigo Mastercard"],
        ["Simon&Schuster", "Simon & Schuster"],
        ["Acme Inc.'s", "Acme Inc", "Acme", "The Acme Corporation"],
        ["Adaire (no reply)", "Adaire", "Adaire - Do Not Reply"],
        ["ООО «Балтийская Логистика»", "Балтийская Логистика"],
        ["Strosser, Stephen", "Stephen Strosser"],
        ["Bolton, Nick E.", "Nick E Bolton"],
        ["Mr. Bolton", "Bolton"],
        ["insuri\U000e001dfy", "Insurify", "insuri\U000e0050fy"],
        ["Optima Tax Relief឴឴", "Optima Tax Relief"],
    ],
)
def test_formatting_variants_share_a_name_group(variants):
    assert len({normalize_name(v) for v in variants}) == 1


@pytest.mark.parametrize("name", ["Ник Болтон", "王小明", "O'Neil", "Nick B", "Inc", "The", "Smith & Co", "Mr"])
def test_distinct_names_keep_their_letters(name):
    assert normalize_name(name).replace("'", "").replace(" ", "") == name.casefold().replace("'", "").replace(" ", "")


@pytest.mark.parametrize(
    ("surface", "kept"),
    [("Nick Bolton's", "Nick Bolton"), ('"Acme Inc."', "Acme Inc."), ("«Ник»", "Ник"), ("Nick B.", "Nick B.")],
)
def test_trim_name_span_keeps_the_name_as_written(surface, kept):
    start, end = trim_name_span(surface)
    assert surface[start:end] == kept


def test_line_breaks_are_word_breaks():
    """A name or address split over lines keeps its words apart."""
    assert (
        normalize_name("3141 Chestnut Street\n\nPhiladelphia, PA 19104") == "3141 chestnut street philadelphia pa 19104"
    )
    assert normalize_name("Acme\tCorp") == normalize_name("Acme Corp")


@pytest.mark.parametrize(
    ("value", "key"), [("Roku, Inc", "roku"), ("Newark, NJ", "newark nj"), ("Washington, DC", "washington dc")]
)
def test_comma_forms_that_are_not_people_keep_their_order(value, key):
    assert normalize_name(value) == key
