import pytest

from cipher.names import compare_names, parse_name
from cipher.names.compare import Level


@pytest.mark.parametrize(
    ("a", "b", "level"),
    [
        ("EF Bolton", "Edmond F Bolton", Level.EXACT),
        ("Austin C Wells", "Austin D Wells", Level.CONFLICT),
        ("Nick C Bolton", "Nicholas C Bolton", Level.EXACT),
        ("Donald Trump Jr", "Donald Trump", Level.MODERATE),
        ("Donald Trump Jr", "Donald Trump Sr", Level.CONFLICT),
        ("Ivan Petrovich Sidorov", "Ivan Sergeyevich Sidorov", Level.CONFLICT),
        ("Ivan Petrovich Sidorov", "Ivan Sidorov", Level.EXACT),
        ("Mr. Bolton", "Nick Bolton", Level.MODERATE),
        ("Mr. Bolton", "Ms. Bolton", Level.CONFLICT),
        ("Mary Smith-Jones", "Mary Smith", Level.STRONG),
    ],
)
def test_name_details(a, b, level):
    assert compare_names(a, b).level == level


def test_lone_word_is_a_surname_when_the_data_says_so():
    assert compare_names("Bolton", "Nick Bolton").level == Level.NONE
    assert compare_names("Bolton", "Nick Bolton", surname_words=frozenset({"bolton"})).level == Level.MODERATE


@pytest.mark.parametrize(
    ("name", "given", "patronymic", "surname"),
    [
        ("EF Bolton", ("e",), None, "bolton"),
        ("NICK BOLTON", ("nick",), None, "bolton"),
        ("Ahmed bin Khalid Al-Saud", ("ahmed",), "khalid", "saud"),
        ("Sidorov Ivan Petrovich", ("ivan",), "petrovich", "sidorov"),
        ("Hans Dietrich Bolton", ("hans",), None, "bolton"),
    ],
)
def test_parse_shapes(name, given, patronymic, surname):
    parsed = parse_name(name)
    assert (parsed.given, parsed.patronymic, parsed.primary_surname) == (given, patronymic, surname)
