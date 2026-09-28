"""Stage 2 -- context scoring."""

from pyselectors.context import ContextScorer

from cipher.schemas.graph.ontology import SelectorType


def _score(lang, selector_type, text, cue_len_left):
    scorer = ContextScorer.for_language(lang)
    # place a fake match right after the left context
    start = cue_len_left
    end = cue_len_left + 4
    return scorer.score(selector_type, text, start, end, base=0.5)


def test_no_cue_returns_base():
    """No cue returns base."""
    scorer = ContextScorer.for_language("en")
    assert scorer.score(SelectorType.PHONE, "......1234......", 6, 10, base=0.5) == 0.5


def test_positive_cue_lifts():
    """Positive cue lifts."""
    scorer = ContextScorer.for_language("en")
    text = "call 1234 now"
    lifted = scorer.score(SelectorType.PHONE, text, 5, 9, base=0.5)
    assert lifted > 0.5


def test_negative_cue_lowers():
    """Negative cue lowers."""
    scorer = ContextScorer.for_language("en")
    text = "invoice 1234 attached"
    lowered = scorer.score(SelectorType.PHONE, text, 8, 12, base=0.5)
    assert lowered < 0.5


def test_window_boundary_respected():
    """Window boundary respected."""
    scorer = ContextScorer.for_language("en")
    far = "call" + " " * 60 + "1234"
    near = " " * 60 + "call 1234"
    s_far = scorer.score(SelectorType.PHONE, far, len(far) - 4, len(far), base=0.5)
    s_near = scorer.score(SelectorType.PHONE, near, len(near) - 4, len(near), base=0.5)
    assert s_far == 0.5  # cue is outside window_before
    assert s_near > 0.5


def test_non_latin_cues():
    """Non latin cues."""
    ru = ContextScorer.for_language("ru")
    assert ru.score(SelectorType.PHONE, "звоните 1234", 8, 12, base=0.5) > 0.5
    zh = ContextScorer.for_language("zh")
    assert zh.score(SelectorType.CRYPTO_ADDRESS, "钱包 abcd", 3, 7, base=0.4) > 0.4
    fa = ContextScorer.for_language("fa")
    assert fa.score(SelectorType.PHONE, "موبایل 1234", 7, 11, base=0.5) > 0.5
