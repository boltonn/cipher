"""Script detection."""

from cipher.names.script import Script, dominant_script, script_histogram


def test_latin():
    """Latin name -> LATIN."""
    assert dominant_script("Nick Bolton") is Script.LATIN


def test_cyrillic():
    """Cyrillic name -> CYRILLIC."""
    assert dominant_script("Владимир Путин") is Script.CYRILLIC


def test_arabic():
    """Arabic name -> ARABIC."""
    assert dominant_script("محمد بن سلمان") is Script.ARABIC


def test_han():
    """Han name -> HAN."""
    assert dominant_script("习近平") is Script.HAN


def test_hangul():
    """Hangul name -> HANGUL."""
    assert dominant_script("김정은") is Script.HANGUL


def test_mixed_takes_majority():
    """A mostly-Latin string with one Cyrillic letter still reads LATIN."""
    assert dominant_script("Ivan Petrov (Иван)") is Script.LATIN


def test_empty_and_digits_are_other():
    """No letters -> OTHER."""
    assert dominant_script("") is Script.OTHER
    assert dominant_script("12345") is Script.OTHER


def test_histogram_counts_letters_only():
    """Histogram ignores spaces and punctuation."""
    hist = script_histogram("Ann-Marie")
    assert hist == {Script.LATIN: 8}
