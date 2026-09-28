"""Culture-aware name parsing."""

from cipher.names.culture import Culture
from cipher.names.parse import parse_name


def test_western_first_last():
    """Generic western: first token given, last token surname."""
    p = parse_name("Nicholas Bolton")
    assert p.given == ("nicholas",)
    assert p.primary_surname == "bolton"


def test_western_comma_form():
    """'Surname, Given' is reordered."""
    p = parse_name("Bolton, Nicholas R.")
    assert p.given_primary == "nicholas"
    assert p.primary_surname == "bolton"


def test_western_honorific_and_suffix_stripped():
    """Honorific prefix and generational suffix are pulled off the body."""
    p = parse_name("Dr. James Robert Bolton Jr.")
    assert p.prefixes == ("dr",)
    assert p.suffixes == ("jr",)
    assert p.given_primary == "james"
    assert p.primary_surname == "bolton"


def test_western_particle_joins_surname_zone():
    """A nobiliary particle is separated from the matchable tokens."""
    p = parse_name("Ludwig van Beethoven")
    assert "van" in p.particles
    assert p.primary_surname == "beethoven"
    assert p.given_primary == "ludwig"


def test_east_slavic_running_order():
    """'Given Patronymic Surname' is detected via the patronymic suffix."""
    p = parse_name("Vladimir Vladimirovich Putin", culture=Culture.EAST_SLAVIC)
    assert p.given_primary == "vladimir"
    assert p.patronymic == "vladimirovich"
    assert p.primary_surname == "putin"


def test_east_slavic_document_order():
    """'Surname Given Patronymic' (patronymic last) is also handled."""
    p = parse_name("Putin Vladimir Vladimirovich", culture=Culture.EAST_SLAVIC)
    assert p.primary_surname == "putin"
    assert p.given_primary == "vladimir"
    assert p.patronymic == "vladimirovich"


def test_east_slavic_two_token():
    """Two tokens -> given + surname."""
    p = parse_name("Olena Kovalchuk", culture=Culture.EAST_SLAVIC)
    assert p.given_primary == "olena"
    assert p.primary_surname == "kovalchuk"


def test_hispanic_double_surname():
    """Paternal surname is the primary; maternal is retained but secondary."""
    p = parse_name("José García Hernández", culture=Culture.HISPANIC)
    assert p.given_primary == "jose"
    assert p.surnames == ("garcia", "hernandez")
    assert p.primary_surname == "garcia"


def test_hispanic_particle_surname():
    """'de la Cruz' — particles pulled, Cruz is the surname."""
    p = parse_name("María de la Cruz", culture=Culture.HISPANIC)
    assert p.given_primary == "maria"
    assert p.primary_surname == "cruz"


def test_lusophone_primary_is_last():
    """Portuguese: the paternal (primary) surname is last."""
    p = parse_name("Maria da Silva Santos", culture=Culture.LUSOPHONE)
    assert p.given_primary == "maria"
    assert p.primary_surname == "santos"


def test_arabic_nasab_chain():
    """bin/ibn and the al- article are treated as particles."""
    p = parse_name("Mohammed bin Salman Al Saud", culture=Culture.ARABIC)
    assert p.given_primary == "mohammed"
    assert "bin" in p.particles
    assert p.primary_surname == "saud"


def test_cjk_family_first_spaced():
    """Family name leads when tokens are space-separated."""
    p = parse_name("Xi Jinping", culture=Culture.CJK)
    assert p.primary_surname == "xi"
    assert p.given == ("jinping",)


def test_cjk_single_han_token():
    """A single 2-4 char Han token splits into surname char + given."""
    p = parse_name("习近平", culture=Culture.CJK)
    assert p.primary_surname == "习"
    assert p.given == ("近平",)


def test_icelandic_patronymic_no_surname():
    """Icelandic: patronymic, no inherited surname."""
    p = parse_name("Björk Guðmundsdóttir", culture=Culture.ICELANDIC)
    assert p.given_primary == "bjork"
    assert p.patronymic is not None
    assert p.primary_surname is None


def test_inference_from_script():
    """With no explicit culture, Cyrillic input infers east_slavic; fields stay in-script."""
    p = parse_name("Владимир Владимирович Путин")
    assert p.culture is Culture.EAST_SLAVIC
    assert p.patronymic == "владимирович"
    assert p.primary_surname == "путин"


def test_empty_name():
    """Empty input parses to an empty ParsedName without error."""
    p = parse_name("")
    assert p.all_tokens == ()
