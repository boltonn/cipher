from pyselectors import extract_selectors
from pyselectors.schemas import SelectorKind


def _kinds(text: str, **kw) -> set[SelectorKind]:
    return {s.selector_kind for s in extract_selectors(text, **kw)}


def test_email_extraction_and_offsets():
    """Email is matched, lowercased, and offsets index back to the raw span."""
    text = "reach me at Jo.Smith@Acme.CO.UK tomorrow"
    spans = extract_selectors(text)
    assert len(spans) == 1
    span = spans[0]
    assert span.selector_kind is SelectorKind.EMAIL
    assert span.normalized_value == "jo.smith@acme.co.uk"
    assert text[span.start_offset : span.end_offset] == "Jo.Smith@Acme.CO.UK"


def test_phone_e164_with_region_hint():
    """A national-format number resolves to E.164 given a region hint."""
    spans = extract_selectors("call 020 7946 0958 tonight", language="en", region="GB")
    phones = [s for s in spans if s.selector_kind is SelectorKind.PHONE]
    assert phones and phones[0].normalized_value == "+442079460958"


def test_phone_international_without_region():
    """An international-format number resolves without any region hint."""
    spans = extract_selectors("+44 20 7946 0958")
    phones = [s for s in spans if s.selector_kind is SelectorKind.PHONE]
    assert phones and phones[0].normalized_value == "+442079460958"


def test_iban_validated():
    """IBANs are matched only when the mod-97 checksum passes."""
    assert SelectorKind.IBAN in _kinds("IBAN GB82 WEST 1234 5698 7654 32 please")
    assert SelectorKind.IBAN not in _kinds("GB00 WEST 1234 5698 7654 32")  # bad checksum


def test_imei_luhn():
    """IMEIs are matched only when the Luhn check passes."""
    assert SelectorKind.IMEI in _kinds("device imei 490154203237518")
    assert SelectorKind.IMEI not in _kinds("device imei 490154203237510")  # bad Luhn


def test_empty_text():
    """Empty input yields no spans."""
    assert extract_selectors("") == []
