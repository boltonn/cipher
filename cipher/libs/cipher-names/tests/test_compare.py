"""Culture-aware name comparison."""

from cipher.names.compare import Level, compare_names
from cipher.names.culture import Culture


def test_identical():
    """Same string -> EXACT."""
    assert compare_names("Nick Bolton", "Nick Bolton").level is Level.EXACT


def test_folded_equal():
    """Case/diacritic-only difference -> EXACT."""
    assert compare_names("JOSÉ GARCÍA", "jose garcia", culture=Culture.HISPANIC).level is Level.EXACT


def test_cross_script_translit_equal():
    """A Cyrillic name and its romanization -> at least STRONG."""
    assert compare_names("Иван Петров", "Ivan Petrov").level >= Level.STRONG


def test_nickname_same_surname():
    """Nickname + same surname -> STRONG."""
    assert compare_names("Bob Bolton", "Robert Bolton").level is Level.STRONG


def test_initial_same_surname():
    """Initial vs full given, same surname -> STRONG."""
    assert compare_names("J. Bolton", "James Bolton").level is Level.STRONG


def test_patronymic_dropped_still_matches():
    """Slavic: full tria nomina vs given+surname -> STRONG (patronymic ignored)."""
    c = compare_names("Vladimir Vladimirovich Putin", "Vladimir Putin", culture=Culture.EAST_SLAVIC)
    assert c.level >= Level.STRONG


def test_gendered_surname_pair():
    """Slavic gendered surname forms are treated as the same surname."""
    c = compare_names("Ivan Kuznetsov", "Ivana Kuznetsova", culture=Culture.EAST_SLAVIC)
    assert c.components["surname"] in {"gendered", "exact"}


def test_hispanic_dropped_maternal_surname():
    """Paternal surname match with maternal dropped -> STRONG."""
    c = compare_names("José García Hernández", "José García", culture=Culture.HISPANIC)
    assert c.level >= Level.STRONG


def test_different_surname_and_given_is_conflict():
    """No component agrees -> CONFLICT (a hard veto)."""
    assert compare_names("Nick Bolton", "Sarah Whitfield").level is Level.CONFLICT


def test_same_given_different_surname_is_weak_not_conflict():
    """Shared given, different surname -> WEAK (maiden/married/typo), never CONFLICT."""
    c = compare_names("Maria Schmidt", "Maria Fischer")
    assert c.level is Level.WEAK


def test_same_surname_different_given_is_moderate():
    """Same surname, different given (sibling?) -> MODERATE, surfaced not vetoed."""
    c = compare_names("Nick Bolton", "Cathi Bolton")
    assert c.level is Level.MODERATE


def test_missing_surname_one_side():
    """One mononym vs a full name: given exact -> MODERATE."""
    c = compare_names("Vladimir", "Vladimir Putin")
    assert c.level is Level.MODERATE


def test_surname_initial_compatible():
    """'Nick Bolton' vs 'Nick B': given exact + surname initial -> MODERATE, not differ/CONFLICT."""
    c = compare_names("Nick Bolton", "Nick B")
    assert c.components["surname"] == "initial"
    assert c.level is Level.MODERATE


def test_surname_initial_without_given_match_is_conflict():
    """'Vivian Battle' vs 'Nick B': a lone initial is not a surname match -> CONFLICT."""
    c = compare_names("Vivian Battle", "Nick B")
    assert c.level is Level.CONFLICT
