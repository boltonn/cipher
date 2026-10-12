"""Window planning: full coverage, overlap, and cuts only at natural breaks."""

import re

from nerd.windows import break_strengths, plan_windows


def _tokens(text: str) -> tuple[list[tuple[int, int]], list[int | None]]:
    """A toy tokenizer: words split into 3-char pieces, punctuation on its own."""
    offsets, word_ids = [], []
    for word_id, m in enumerate(re.finditer(r"\w+|[^\w\s]", text)):
        for start in range(m.start(), m.end(), 3):
            offsets.append((start, min(start + 3, m.end())))
            word_ids.append(word_id)
    return offsets, word_ids


def _plan(text: str, budget: int = 40, overlap: int = 12):
    offsets, word_ids = _tokens(text)
    strengths = break_strengths(text, offsets, word_ids)
    return offsets, word_ids, strengths, plan_windows(strengths, budget, overlap)


def test_short_text_is_one_window():
    """A text that fits is read in one piece, as before."""
    *_, windows = _plan("Megan Flick wrote to Nick.")
    assert len(windows) == 1


def test_windows_cover_every_token_and_overlap():
    """Every token is read, and each cut is read again by the next window."""
    text = " ".join(f"Sentence number {i} mentions Megan Flick today." for i in range(40))
    offsets, _, _, windows = _plan(text)
    covered = set().union(*(range(s, e) for s, e in windows))
    assert covered == set(range(len(offsets)))
    assert all(nxt_start < end for (_, end), (nxt_start, _) in zip(windows, windows[1:], strict=False))
    assert all(e - s <= 40 for s, e in windows)


def test_never_cut_mid_word():
    """No window starts or ends inside a word, even in one long unpunctuated line."""
    text = " ".join(["Megalomaniacal Flickering"] * 120)
    _, word_ids, _, windows = _plan(text)
    for start, end in windows:
        assert start == 0 or word_ids[start] != word_ids[start - 1]
        assert end == len(word_ids) or word_ids[end] != word_ids[end - 1]


def test_prefers_line_and_sentence_breaks():
    """With line breaks available, every cut lands on one."""
    text = "\n".join(f"On Fri, Megan Flick <megan{i}@example.com> wrote:" for i in range(30))
    offsets, _, strengths, windows = _plan(text, budget=64, overlap=32)
    for start, end in windows:
        assert start == 0 or strengths[start] >= 3
        assert end == len(offsets) or strengths[end] >= 3


def test_one_giant_word_still_progresses():
    """An unbreakable run (glued text, unspaced CJK) falls back to fixed cuts and still finishes."""
    text = "x" * 600
    offsets, _, _, windows = _plan(text)
    assert windows[-1][1] == len(offsets)
    assert set().union(*(range(s, e) for s, e in windows)) == set(range(len(offsets)))


def test_dot_inside_an_address_is_not_a_sentence_end():
    """`megan.e.flick@gmail.com` has no sentence break; `wrote. Then` and `。` do."""
    for text, expect in [("megan.e.flick@gmail.com", False), ("wrote. Then", True), ("你好。我们", True)]:
        offsets, word_ids = _tokens(text)
        assert (2 in break_strengths(text, offsets, word_ids)) is expect, text


def test_no_tokens_no_windows():
    """A text with nothing left to read (a bare URL, masked to blanks) plans no windows."""
    assert break_strengths("   ", [], []) == []
    assert plan_windows([], budget=40, overlap=12) == []
