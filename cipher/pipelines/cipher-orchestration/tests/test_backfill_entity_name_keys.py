"""Pure-logic tests for entity_name_key population (no DB)."""

from cipher.datastores.postgres.repositories.entity_name_key import _pairs_for
from cipher.schemas.graph.ontology import EntityType


def test_person_gets_keyed():
    """A person entity yields blocking-key pairs from its display name."""
    pairs = _pairs_for(EntityType.PERSON, "Nicholas Bolton", [])
    assert ("folded", "nicholas bolton") in pairs
    assert ("surname", "bolton") in pairs


def test_aliases_contribute_keys():
    """Alias surnames become their own surname keys."""
    pairs = _pairs_for(EntityType.PERSON, "Olena Kovalchuk", ["Olena Shevchenko"])
    surnames = {v for t, v in pairs if t == "surname"}
    assert {"kovalchuk", "shevchenko"} <= surnames


def test_selector_entities_are_not_keyed():
    """Selectors resolve by exact value, not by name -- no key rows."""
    assert _pairs_for(EntityType.SELECTOR, "noreply@medium.com", []) == set()


def test_organization_is_keyed():
    """Organizations are keyed too."""
    pairs = _pairs_for(EntityType.ORGANIZATION, "Acme Corporation", [])
    assert ("folded", "acme corporation") in pairs


def test_blank_display_name_is_safe():
    """An empty display name yields no pairs, not an error."""
    assert _pairs_for(EntityType.PERSON, "", []) == set()
