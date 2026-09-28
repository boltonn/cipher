"""String folding."""

from cipher.names.normalize import fold, tokens


def test_diacritics_stripped_latin():
    """Latin diacritics are removed."""
    assert fold("José García Hernández") == "jose garcia hernandez"


def test_case_and_whitespace():
    """Casefold and whitespace collapse."""
    assert fold("  Nick   BOLTON ") == "nick bolton"


def test_non_latin_scripts_pass_through():
    """Cyrillic is not transliterated by fold()."""
    assert fold("Владимир") == "владимир"


def test_format_characters_removed():
    """Zero-width and bidi-control characters are dropped."""
    assert fold("Nick​Bolton‎") == "nickbolton"


def test_nfkc_ligatures_and_fullwidth():
    """Compatibility forms are normalized."""
    assert fold("ﬁnn") == "finn"
    assert fold("ＮＩＣＫ") == "nick"


def test_tokens_split_on_punctuation():
    """Tokenizer breaks on commas, dots, hyphens, apostrophes."""
    assert tokens("Bolton, Nick R.") == ["bolton", "nick", "r"]
    assert tokens("Anne-Marie O'Brien") == ["anne", "marie", "o", "brien"]
