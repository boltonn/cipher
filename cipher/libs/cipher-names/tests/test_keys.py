"""Blocking-key generation."""

from cipher.names.culture import Culture
from cipher.names.keys import blocking_keys, entity_keys


def test_latin_name_keys():
    """A plain Latin name yields the core keys."""
    k = blocking_keys("Nicholas Bolton")
    assert k["folded"] == "nicholas bolton"
    assert k["translit"] == "nicholas bolton"
    assert k["sorted_tokens"] == "bolton nicholas"
    assert k["surname"] == "bolton"
    assert k["given_surname"] == "nicholas bolton"


def test_initials_only_for_three_or_more_tokens():
    """A 2-token name is too common on initials to index; a 3-token one is not."""
    assert "initials" not in blocking_keys("Nick Bolton")
    assert blocking_keys("James Robert Bolton")["initials"] == "jrb"


def test_word_order_shares_sorted_tokens_key():
    """'Bolton Nick' and 'Nick Bolton' collide on sorted_tokens."""
    a = blocking_keys("Nick Bolton")
    b = blocking_keys("Bolton, Nick")
    assert a["sorted_tokens"] == b["sorted_tokens"]


def test_cross_script_shares_translit_key():
    """A Cyrillic name and its romanization collide on translit."""
    a = blocking_keys("Иван Петров")
    b = blocking_keys("Ivan Petrov")
    assert a["translit"] == b["translit"]


def test_spelling_variants_share_phonetic_key():
    """Romanization spelling variants collide on phonetic."""
    a = blocking_keys("Kovalchuk")
    b = blocking_keys("Kowalchuk")
    assert a["phonetic"] == b["phonetic"]


def test_patronymic_stripped_given_surname_key():
    """The given_surname key drops the patronymic for East-Slavic names."""
    full = blocking_keys("Vladimir Vladimirovich Putin", culture=Culture.EAST_SLAVIC)
    short = blocking_keys("Vladimir Putin", culture=Culture.EAST_SLAVIC)
    assert full["given_surname"] == short["given_surname"] == "vladimir putin"


def test_hispanic_surname_key_is_paternal():
    """The surname key is the paternal (primary) surname only."""
    k = blocking_keys("José García Hernández", culture=Culture.HISPANIC)
    assert k["surname"] == "garcia"


def test_empty_name_yields_no_keys():
    """Empty input -> empty dict."""
    assert blocking_keys("") == {}


def test_entity_keys_is_pair_set():
    """entity_keys returns a set of (key_type, key) tuples for the display name."""
    keys = entity_keys("Nicholas Bolton")
    assert ("folded", "nicholas bolton") in keys
    assert ("surname", "bolton") in keys
    assert all(isinstance(p, tuple) and len(p) == 2 for p in keys)


def test_entity_keys_merges_aliases():
    """Alias-derived keys are unioned in; a maiden name becomes its own surname key."""
    keys = entity_keys("Olena Kovalchuk", ["Olena Shevchenko", "О. Ковальчук"])
    surnames = {v for t, v in keys if t == "surname"}
    assert {"kovalchuk", "shevchenko"} <= surnames


def test_entity_keys_dedups_and_ignores_blank_aliases():
    """Repeated/blank aliases don't multiply the set."""
    plain = entity_keys("Nick Bolton")
    with_dupes = entity_keys("Nick Bolton", ["Nick Bolton", "", "  "])
    assert plain == with_dupes


def test_entity_keys_capped():
    """A pathological alias list can't blow past the per-entity cap."""
    aliases = [f"Person Number {i}" for i in range(200)]
    assert len(entity_keys("Real Name", aliases)) <= 64
