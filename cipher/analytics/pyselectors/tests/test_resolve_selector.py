"""Retroactive single-value resolution (normalize + validate + attributes)."""

from pyselectors import resolve_selector

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType


def test_forced_type_normalizes_and_validates():
    """Forced type normalizes and validates."""
    (span,) = resolve_selector("Foo@Bar.COM", selector_type=SelectorType.EMAIL)
    assert span.normalized_value == "foo@bar.com"
    assert span.attributes["domain"] == "bar.com"
    assert span.confidence == 1.0
    assert (span.start_offset, span.end_offset) == (0, len("Foo@Bar.COM"))


def test_forced_type_returns_empty_on_bad_value():
    """Forced type returns empty on bad value."""
    assert resolve_selector("GB00 WEST 1234 5698 7654 32", selector_type=SelectorType.IBAN) == []


def test_forced_type_with_region_for_phone():
    """Forced type with region for phone."""
    (span,) = resolve_selector("020 7946 0958", selector_type=SelectorType.PHONE, region="GB")
    assert span.normalized_value == "+442079460958"
    assert span.attributes["region"] == "GB"


def test_forced_national_id_uses_region():
    """Forced national id uses region."""
    (span,) = resolve_selector("7830002293", selector_type=SelectorType.NATIONAL_ID, region="RU")
    assert span.attributes["subtype"] == "ru_inn"


def test_inference_when_type_omitted():
    """Inference when type omitted."""
    spans = resolve_selector("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")
    assert spans and spans[0].selector_type is SelectorType.CRYPTO_ADDRESS
    assert spans[0].selector_subtype is SelectorSubtype.BTC_ADDRESS


def test_inference_blank_is_empty():
    """Inference blank is empty."""
    assert resolve_selector("   ") == []
