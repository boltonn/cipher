"""Transliteration to ASCII Latin."""

from cipher.names.translit import backend, to_latin


def test_backend_is_known():
    """The active tier is one of the three expected values."""
    assert backend() in {"icu", "anyascii", "builtin"}


def test_ascii_passthrough():
    """Already-Latin input is only lowercased."""
    assert to_latin("Nick Bolton") == "nick bolton"


def test_cyrillic():
    """Cyrillic romanizes to recognizable Latin."""
    out = to_latin("Владимир")
    assert out.startswith("vladimir") or out.startswith("vladimyr")


def test_diacritics_folded_to_ascii():
    """Latin diacritics collapse to ASCII."""
    assert to_latin("José") == "jose"


def test_greek():
    """Greek romanizes to ascii starting with g."""
    out = to_latin("Γιώργος")
    assert out.isascii() and out.startswith("g")


def test_result_is_pure_ascii():
    """Output never contains non-ASCII."""
    for name in ("محمد", "习近平", "Владимир", "Åse Bjørn"):
        assert to_latin(name).isascii()


def test_empty():
    """Empty in, empty out."""
    assert to_latin("") == ""
