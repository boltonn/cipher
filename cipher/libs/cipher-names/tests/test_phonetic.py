"""Phonetic keys."""

from cipher.names.phonetic import backend, phonetic_key, phonetic_token


def test_backend_is_known():
    """The active tier is one of the expected values."""
    assert backend() in {"jellyfish", "builtin"}


def test_spelling_variants_collapse():
    """Common surname spelling variants share a key."""
    assert phonetic_token("smith") == phonetic_token("smyth")


def test_transliterated_variants_collapse():
    """Romanization variants of a Slavic surname share a key."""
    assert phonetic_key("Kovalchuk") == phonetic_key("Kowalchuk")


def test_word_order_matters():
    """Phonetic key keeps token order (it is a per-token join)."""
    assert phonetic_key("Nick Bolton") != phonetic_key("Bolton Nick")


def test_cross_script_via_translit():
    """A Cyrillic name and its romanization produce the same key."""
    assert phonetic_key("Иван") == phonetic_key("Ivan")


def test_empty():
    """Empty in, empty out."""
    assert phonetic_key("") == ""
    assert phonetic_token("") == ""
