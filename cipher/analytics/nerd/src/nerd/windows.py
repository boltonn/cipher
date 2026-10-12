"""Plan the encoder windows a long text is read through.

Windows are cut only where text naturally breaks -- a paragraph, then a line,
then a sentence end, then any word boundary; never inside a word unless a
single "word" (glued text, an unspaced CJK run) outgrows a window. Consecutive
windows also overlap, so with max-context stitching every token near a cut is
read again with context on both sides: a cut placed at a wrong boundary guess
("Dr. | Smith") still can't truncate an entity.
"""

# a sentence ends at one of these followed by whitespace (not the "." in megan.e.flick@gmail.com) ...
_SENTENCE_END = frozenset(".!?;؟।…")
# ... or at full-width CJK punctuation, which no space follows
_CJK_SENTENCE_END = frozenset("。！？；")

# break strength between token i-1 and token i (a window may start at i)
_MID_WORD, _WORD, _SENTENCE, _LINE, _PARAGRAPH = 0, 1, 2, 3, 4


def break_strengths(text: str, offsets: list[tuple[int, int]], word_ids: list[int | None]) -> list[int]:
    """How cleanly the text breaks just before each token."""
    if not offsets:
        return []
    strengths = [_PARAGRAPH]
    for i in range(1, len(offsets)):
        prev_end, start = offsets[i - 1][1], offsets[i][0]
        gap = text[prev_end:start]
        if gap.count("\n") >= 2:
            strengths.append(_PARAGRAPH)
        elif "\n" in gap:
            strengths.append(_LINE)
        elif prev_end and ((gap and text[prev_end - 1] in _SENTENCE_END) or text[prev_end - 1] in _CJK_SENTENCE_END):
            strengths.append(_SENTENCE)
        elif gap or word_ids[i] is None or word_ids[i] != word_ids[i - 1]:
            strengths.append(_WORD)
        else:
            strengths.append(_MID_WORD)
    return strengths


def _best_cut(strengths: list[int], lo: int, hi: int, *, latest: bool) -> int:
    """The strongest break in [lo, hi], ties to the latest (or earliest); ``hi`` when there's none."""
    best = max(range(lo, hi + 1), key=lambda i: (strengths[i], i if latest else -i))
    return best if strengths[best] > _MID_WORD else hi


def plan_windows(strengths: list[int], budget: int, overlap: int) -> list[tuple[int, int]]:
    """``[start, end)`` token ranges of at most ``budget`` tokens covering every token.

    Each window ends at the strongest break in its last half (as late as possible); the
    next starts at the strongest break ``overlap`` to ``overlap / 2`` tokens before that
    end (as early as possible), so a token beside a cut always keeps context in one window.
    """
    n = len(strengths)
    windows: list[tuple[int, int]] = []
    start = 0
    while n:
        if n - start <= budget:
            windows.append((start, n))
            return windows
        end = _best_cut(strengths, start + budget // 2, start + budget, latest=True)
        windows.append((start, end))
        start = max(_best_cut(strengths, end - overlap, end - overlap // 2, latest=False), start + 1)
    return windows
