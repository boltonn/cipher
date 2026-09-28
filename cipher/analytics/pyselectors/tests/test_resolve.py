"""Stage 5 -- overlap resolution."""

from pyselectors.resolve import resolve

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType
from cipher.schemas.graph.spans import SelectorSpan


def _span(selector_type, start, end, conf=0.8, subtype=None):
    return SelectorSpan(
        selector_type=selector_type,
        selector_subtype=subtype,
        raw_value="x" * (end - start),
        normalized_value="x",
        start_offset=start,
        end_offset=end,
        confidence=conf,
    )


def test_non_overlapping_all_kept():
    """Non overlapping all kept."""
    spans = [_span(SelectorType.EMAIL, 0, 10), _span(SelectorType.PHONE, 20, 32)]
    assert len(resolve(spans)) == 2


def test_higher_priority_wins_overlap():
    """Higher priority wins overlap."""
    iban = _span(SelectorType.IBAN, 0, 20, conf=0.9)
    phone = _span(SelectorType.PHONE, 2, 18, conf=0.95)
    (kept,) = resolve([phone, iban])
    assert kept.selector_type is SelectorType.IBAN


def test_subtype_beats_umbrella_same_type():
    """Subtype beats umbrella same type."""
    umbrella = _span(SelectorType.CRYPTO_ADDRESS, 0, 34, conf=0.8)
    specific = _span(SelectorType.CRYPTO_ADDRESS, 0, 34, conf=0.8, subtype=SelectorSubtype.BTC_ADDRESS)
    (kept,) = resolve([umbrella, specific])
    assert kept.selector_subtype is SelectorSubtype.BTC_ADDRESS


def test_handle_inside_email_dropped():
    """Handle inside email dropped."""
    email = _span(SelectorType.EMAIL, 0, 20, conf=0.9)
    handle = _span(SelectorType.SOCIAL_HANDLE, 5, 12, conf=0.5)
    (kept,) = resolve([email, handle])
    assert kept.selector_type is SelectorType.EMAIL


def test_confidence_breaks_priority_tie():
    """Confidence breaks priority tie."""
    a = _span(SelectorType.EMAIL, 0, 10, conf=0.6)
    b = _span(SelectorType.EMAIL, 0, 10, conf=0.9)
    (kept,) = resolve([a, b])
    assert kept.confidence == 0.9
