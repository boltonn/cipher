from pyprompt.offsets import OffsetResolver


def test_locates_first_occurrence():
    r = OffsetResolver("Alice met Bob in Paris.")
    assert r.locate("Alice") == (0, 5)
    assert r.locate("Paris") == (17, 22)


def test_repeated_surface_claims_successive_spans():
    r = OffsetResolver("Bob called Bob about Bob.")
    assert r.locate("Bob") == (0, 3)
    assert r.locate("Bob") == (11, 14)
    assert r.locate("Bob") == (21, 24)
    assert r.locate("Bob") is None


def test_case_insensitive_fallback():
    r = OffsetResolver("the ACME Corporation shipped it")
    assert r.locate("acme corporation") == (4, 20)


def test_missing_surface_returns_none():
    r = OffsetResolver("nothing to see here")
    assert r.locate("Zurich") is None


def test_blank_surface_returns_none():
    assert OffsetResolver("abc").locate("   ") is None
