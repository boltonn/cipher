import re

import pytest

from cipher.orchestration.extract_signatures import authored_text, is_farewell
from cipher.orchestration.signature_cues import FAREWELLS, REPLY_MARKERS


@pytest.mark.parametrize("language", sorted(FAREWELLS))
def test_every_farewell_matches_as_its_own_line(language):
    """Each listed phrase, written on its own line with a trailing comma, is a farewell."""
    for phrase in FAREWELLS[language]:
        assert is_farewell(f"{phrase.title()},"), phrase


@pytest.mark.parametrize("language", sorted(REPLY_MARKERS))
def test_every_reply_marker_compiles(language):
    """Reply markers are regular expressions; a broken one would silently drop a language."""
    for pattern in REPLY_MARKERS[language]:
        re.compile(pattern)


def test_a_farewell_inside_a_sentence_is_not_one():
    """Only a whole line counts, so prose that starts with "Best" or "Thanks" does not."""
    assert not is_farewell("Best of luck with the launch")
    assert not is_farewell("Thanks for sending the berth schedule over")


@pytest.mark.parametrize(
    "marker",
    [
        "On Tue, Jan 3, 2023 at 9:00 AM Rosa wrote:",
        "Am 03.03.2025 um 09:00 schrieb Jonas Becker <j@x.de>:",
        "Le 3 mars 2025 à 09:00, Quentin a écrit :",
        "El 3 mar 2025, Rosa escribió:",
        "-----Original Message-----",
        "发件人: 王伟",
    ],
)
def test_reply_markers_cut_the_quote(marker):
    """Everything from a reply marker down is someone else's text."""
    assert authored_text(f"Ok.\n\n{marker}\n> quoted\n").strip() == "Ok."
