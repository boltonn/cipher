"""Stage 3 -- canonicalization."""

from pyselectors import normalize

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType


def test_fold_digits_length_invariant():
    """Fold digits length invariant."""
    text = "بيت ۱۲۳ و ٤٥٦ end"
    folded = normalize.fold_digits(text)
    assert len(folded) == len(text)
    assert "123" in folded and "456" in folded


def test_region_for_precedence():
    """Region for precedence."""
    assert normalize.region_for(language="ru", region="gb") == "GB"
    assert normalize.region_for(language="fa", region=None) == "IR"
    assert normalize.region_for(language=None, region=None) is None


def test_normalize_email_undefang():
    """Normalize email undefang."""
    assert normalize.normalize_email("A.B [at] Foo [dot] com") == "a.b@foo.com"
    assert normalize.normalize_email("<X@Y.COM>") == "x@y.com"


def test_normalize_iban_compacts_or_none():
    """Normalize iban compacts or none."""
    assert normalize.normalize_iban("GB82 WEST 1234 5698 7654 32") == "GB82WEST12345698765432"
    assert normalize.normalize_iban("GB00 WEST 1234 5698 7654 32") is None


def test_normalize_crypto_lowercases_bech32_keeps_eip55():
    """Normalize crypto lowercases bech32 keeps eip55."""
    got = normalize.canonicalize(
        "crypto_address", "BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4", subtype=SelectorSubtype.BTC_ADDRESS
    )
    assert got == "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
    eip55 = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
    assert normalize.canonicalize("crypto_address", eip55, subtype=SelectorSubtype.ETH_ADDRESS) == eip55


def test_normalize_social_handle_strips_url():
    """Normalize social handle strips url."""
    assert normalize.normalize_social_handle("https://t.me/Durov", subtype=SelectorSubtype.TELEGRAM) == "durov"
    assert normalize.normalize_social_handle("@Alice_99") == "alice_99"


def test_normalize_selector_roundtrip_for_backend():
    """Normalize selector roundtrip for backend."""
    value, attrs = normalize.normalize_selector(SelectorType.EMAIL, "Foo@Bar.COM")
    assert value == "foo@bar.com"
    assert attrs["domain"] == "bar.com"
    bad, _ = normalize.normalize_selector(SelectorType.IBAN, "GB00 WEST 1234 5698 7654 32")
    assert bad is None
