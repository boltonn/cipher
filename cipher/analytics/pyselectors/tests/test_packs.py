"""Structural checks on every shipped pack."""

import pytest
from pyselectors.normalize import NORMALIZERS
from pyselectors.packs.loader import available_pack_names, load_pack
from pyselectors.packs.registry import ENABLED_TYPES
from pyselectors.validate import VALIDATORS

_CONTEXT_LANGS = {"en", "ru", "uk", "zh", "ar", "fa", "es", "fr"}


@pytest.mark.parametrize("name", available_pack_names())
def test_pack_validates_and_wires_up(name):
    """Pack validates and wires up."""
    pack = load_pack(name)
    assert pack.selector_type.value == name
    assert pack.normalizer in NORMALIZERS
    if pack.validator is not None:
        assert pack.validator in VALIDATORS
    for country, override in pack.countries.items():
        assert country.isupper() and len(country) == 2
        if override.validator is not None:
            assert override.validator in VALIDATORS


@pytest.mark.parametrize("name", available_pack_names())
def test_pack_context_languages_known(name):
    """Pack context languages known."""
    pack = load_pack(name)
    assert set(pack.context.terms) <= _CONTEXT_LANGS


def test_every_enabled_type_has_a_pack():
    """Every enabled type has a pack."""
    for selector_type in ENABLED_TYPES:
        load_pack(selector_type.value)  # raises if missing
