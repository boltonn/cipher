"""Stage 1 -- candidate matching + offset fidelity."""

from pyselectors.patterns import find_all

from cipher.schemas.graph.ontology import SelectorType


def _spanned(text, r):
    return text[r.start : r.end]


def test_offsets_index_back_to_text():
    """Offsets index back to text."""
    text = "  a@b.com and 8.8.8.8 done"
    for r in find_all(text):
        assert _spanned(text, r) == text[r.start : r.end]
        assert r.end > r.start


def test_email_and_ip_found():
    """Email and ip found."""
    text = "mail a@b.com host 192.168.0.1"
    types = {r.selector_type for r in find_all(text)}
    assert SelectorType.EMAIL in types
    assert SelectorType.IP in types


def test_cjk_adjacent_number_not_swallowed():
    """Cjk adjacent number not swallowed."""
    text = "电话13800138000联系"
    matches = [r for r in find_all(text, types=(SelectorType.PHONE,))]
    for r in matches:
        assert "电" not in _spanned(text, r) and "联" not in _spanned(text, r)


def test_matches_sorted_by_start():
    """Matches sorted by start."""
    text = "1.2.3.4 then a@b.com then 5.6.7.8"
    rs = find_all(text)
    assert rs == sorted(rs, key=lambda r: (r.start, -(r.end - r.start)))


def test_crypto_pattern_carries_subtype_hint():
    """Crypto pattern carries subtype hint."""
    text = "0x52908400098527886e0f7030069857d2e4169ee7"
    (r,) = find_all(text, types=(SelectorType.CRYPTO_ADDRESS,))
    assert r.selector_subtype is not None
    assert r.hint.get("currency") == "ETH"
