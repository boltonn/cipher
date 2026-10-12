"""Transformers token-classification wrapper producing `EntitySpan`s.

Decoding is offset-based: the model is run over sub-word tokens, predictions
are argmax'd per token, sub-tokens are pooled to whole words (HF's ``"first"``
aggregation -- a word's tag/score come from its first sub-token, but its span
covers all of the word's characters), and BIO runs are merged back to
character spans at word granularity via the tokenizer's offset mapping.

Documents longer than the encoder's 512-token window are tokenized once and
read through overlapping windows cut at natural breaks -- paragraph, line,
sentence, word; never mid-word (`nerd.windows`). They're decoded *once*: each
token takes its prediction from the window where it has the most context on
both sides (BERT's "max context" rule), and BIO merging runs over the stitched
document. A window edge is never a span boundary, so a name straddling it
can't come back as a fragment (``n Flick`` from a window starting mid-``Megan``).

Word-level pooling matters because BIO-run merging treats any ``B-`` tag
preceded by a character gap as the start of a new entity (needed to keep
"John Smith Jane Doe" from gluing into one span). At raw sub-token
granularity, argmax noise on an interior sub-token -- e.g. "Delaware"
tokenizing as "Dela"+"ware" and the second piece flipping to a fresh ``B-``
or dropping to ``O`` -- looks identical to that same signal and truncates the
entity mid-word. Pooling to whole words first means the gap-based split only
ever sees real word boundaries, where the signal is meaningful.
"""

from __future__ import annotations

import re
from typing import Literal

from loguru import logger

from cipher.schemas._base.common import ModelDevice
from nerd.labels import normalize_label
from nerd.schemas import EntitySpan
from nerd.windows import break_strengths, plan_windows

_MAX_TOKENS = 512
_STRIDE = 64

CudaDtype = Literal["float16", "bfloat16", "float32"]

# URLs were never a training label, so the model free-associates on their path
# segments (query strings, %-encoded words) and emits junk location/org spans.
# Blanking them out char-for-char keeps every other span's offset valid.
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

# Per-label score floors over `threshold`. Measured on the rag email corpus (2026-10-12): organization
# and place-name spans scoring 0.5-0.6 are about half fragments and non-entities ("Towards", "of",
# "San", "P.O"), and 84% of their values recur above 0.6 elsewhere. Person spans there are mostly
# real names (quoted reply headers), so they keep the plain threshold.
LABEL_FLOORS: dict[str, float] = {"organization.name": 0.6, "location.name": 0.6}


def _mask_urls(text: str) -> str:
    return _URL_RE.sub(lambda m: " " * len(m.group()), text)


class NerdModel:
    """A fine-tuned token-classification NER model with offset-based span decoding."""

    def __init__(
        self,
        model_dir: str,
        device: ModelDevice = ModelDevice.CPU,
        aggregation_strategy: str = "first",
        dtype: CudaDtype = "float16",
        max_batch_tokens: int = 16384,
    ):
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        if aggregation_strategy != "first":
            raise ValueError(
                f"NerdModel only implements the 'first' aggregation strategy, got {aggregation_strategy!r}"
            )

        self._torch = torch
        self._device = "cuda" if device == ModelDevice.CUDA else "cpu"
        self._max_batch_tokens = max(max_batch_tokens, _MAX_TOKENS)
        self._tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
        torch_dtype = getattr(torch, dtype) if self._device == "cuda" else torch.float32
        model = AutoModelForTokenClassification.from_pretrained(
            model_dir, dtype=torch_dtype, attn_implementation="sdpa"
        )
        self._model = model.to(self._device).eval()
        self._id2label: dict[int, str] = self._model.config.id2label
        logger.info(
            f"✅ nerd model loaded from {model_dir} ({self._device}, {torch_dtype}, "
            f"{len(self._id2label)} tags, offset-decoding)."
        )

    # -- decoding ---------------------------------------------------------

    @staticmethod
    def _split_tag(tag: str) -> tuple[str, str]:
        """``B-person.name`` -> ``("B", "person.name")``; ``O`` -> ``("O", "")``."""
        if tag == "O" or "-" not in tag:
            return ("O", "")
        prefix, _, label = tag.partition("-")
        if prefix not in ("B", "I"):
            return ("B", tag)
        return (prefix, label)

    # Below this fraction of (distinct word ids / real tokens), the tokenizer's
    # word concept isn't meaningful -- e.g. SentencePiece only starts a new
    # "word" at whitespace, so an unspaced CJK/Thai run comes back as a single
    # giant word_id (ratio ~0.05-0.1 for a real sentence). Pooling that would
    # glue the whole run into one entity, so this falls back to one-token-per-
    # word (the original, pre-pooling behaviour, which already handles those
    # scripts correctly via `_merge`'s zero-gap tolerance). Ordinary
    # space-delimited text stays well clear of this even when dense with long
    # words, numbers, or hyphenated codes (an address line with a lot of
    # multi-piece words still measured ~0.43) -- 0.2 only fires on the
    # genuinely no-word-boundary case.
    _MIN_WORD_ID_RATIO = 0.2

    @classmethod
    def _pool_words(
        cls,
        offsets: list[tuple[int, int]],
        tags: list[str],
        scores: list[float],
        word_ids: list[int | None],
    ) -> tuple[list[tuple[int, int]], list[str], list[float]]:
        """Pool sub-word tokens to whole words.

        A word's tag/score come from its first sub-token (HF's ``"first"`` strategy); its span covers every
        sub-token's characters, so a mid-word tag flip can no longer truncate it.
        """
        real = [(o, t, s, w) for o, t, s, w in zip(offsets, tags, scores, word_ids, strict=True) if o[0] != o[1]]
        if not real:
            return [], [], []
        distinct_words = len({w for *_, w in real if w is not None})
        if distinct_words < cls._MIN_WORD_ID_RATIO * len(real):
            return [o for o, *_ in real], [t for _, t, *_ in real], [s for _, _, s, _ in real]

        word_offsets: list[tuple[int, int]] = []
        word_tags: list[str] = []
        word_scores: list[float] = []
        prev_word_id: int | None = None
        for (a, b), tag, sc, wid in real:
            if wid == prev_word_id:
                start, _ = word_offsets[-1]
                word_offsets[-1] = (start, b)
            else:
                word_offsets.append((a, b))
                word_tags.append(tag)
                word_scores.append(sc)
            prev_word_id = wid
        return word_offsets, word_tags, word_scores

    def _merge(
        self,
        text: str,
        offsets: list[tuple[int, int]],
        tags: list[str],
        scores: list[float],
    ) -> list[tuple[int, int, str, float]]:
        """Merge per-token BIO predictions into ``(start, end, label, score)`` spans.

        A run continues while the label is unchanged, *unless* a ``B-`` token is
        separated from the current run by any gap at all -- that starts a new
        entity of the same type (this is what keeps "John Smith Jane Doe" or a
        newline-separated list of company names from gluing into one span).
        Only a *zero*-width gap (contiguous same-label sub-words, e.g. Chinese)
        merges across a repeated ``B-``, which tolerates models that emit only
        ``B-`` for scripts without whitespace word boundaries.
        """
        spans: list[tuple[int, int, str, float]] = []
        cur_label: str | None = None
        cur_start = cur_end = 0
        cur_scores: list[float] = []

        def flush():
            if cur_label is None or cur_end <= cur_start:
                return
            s, e = cur_start, cur_end
            while s < e and not text[s].isalnum():  # trim leading punctuation/space
                s += 1
            while e > s and not text[e - 1].isalnum():  # trim trailing
                e -= 1
            last_line = text[s:e].rsplit("\n", 1)
            if len(last_line) == 2 and len(last_line[1].strip()) == 1:  # "m" / "o" / "e" phone cues under an address
                e = s + len(last_line[0])
                while e > s and not text[e - 1].isalnum():
                    e -= 1
            if e > s:
                spans.append((s, e, cur_label, sum(cur_scores) / len(cur_scores)))

        for (a, b), tag, sc in zip(offsets, tags, scores, strict=True):
            if a == b:  # special token
                continue
            prefix, label = self._split_tag(tag)
            if prefix == "O" or not label:
                flush()
                cur_label, cur_scores = None, []
                continue
            has_gap = cur_label is not None and a > cur_end
            # a name never runs across a line break ("Melissa" / "Lauren Hard"); an address does
            line_break = has_gap and "address" not in label and "\n" in text[cur_end:a]
            continues = cur_label == label and not (prefix == "B" and has_gap) and not line_break
            if continues:
                cur_end = b
                cur_scores.append(sc)
            else:
                flush()
                cur_label, cur_start, cur_end, cur_scores = label, a, b, [sc]
        flush()
        return spans

    def infer(
        self, text: str, threshold: float = 0.5, label_floors: dict[str, float] | None = None
    ) -> list[EntitySpan]:
        """Predict entity spans over `text` (see `infer_batch` for the score floors)."""
        return self.infer_batch([text], threshold=threshold, label_floors=label_floors)[0]

    def _pack(self, lengths: list[int]) -> list[list[int]]:
        """Group window indices, shortest first, into passes of at most `max_batch_tokens` padded tokens."""
        batches: list[list[int]] = []
        for w in sorted(range(len(lengths)), key=lengths.__getitem__):
            if batches and (len(batches[-1]) + 1) * lengths[w] <= self._max_batch_tokens:
                batches[-1].append(w)
            else:
                batches.append([w])
        return batches

    def infer_batch(
        self, texts: list[str], threshold: float = 0.5, label_floors: dict[str, float] | None = None
    ) -> list[list[EntitySpan]]:
        """Predict entity spans for many texts, one result list per text.

        A span is kept when it scores at/above `threshold` and its label's floor
        (`label_floors`, default `LABEL_FLOORS`; pass `{}` for `threshold` alone).

        Each text is tokenized once and read through windows cut at natural breaks
        (`nerd.windows`); windows from every text are length-sorted and packed into
        shared forward passes, then each text's predictions are stitched per token
        (max context) and decoded once.
        """
        torch = self._torch
        live = [i for i, text in enumerate(texts) if text and text.strip()]
        # per text: token index -> (context, tag, score), the best-context window winning
        best: list[dict[int, tuple[int, str, float]]] = [{} for _ in texts]
        encodings: dict[int, tuple[list[int], list[tuple[int, int]], list[int | None]]] = {}
        windows: list[tuple[int, int, int]] = []
        if live:
            enc = self._tokenizer(
                [_mask_urls(texts[i]) for i in live],  # same length -- offsets still index the original
                add_special_tokens=False,
                return_offsets_mapping=True,
                verbose=False,
            )
            budget = _MAX_TOKENS - self._tokenizer.num_special_tokens_to_add()
            for row, i in enumerate(live):
                ids, offsets, word_ids = (
                    enc["input_ids"][row],
                    [tuple(o) for o in enc["offset_mapping"][row]],
                    enc.word_ids(row),
                )
                encodings[i] = (ids, offsets, word_ids)
                strengths = break_strengths(texts[i], offsets, word_ids)
                windows += [(i, start, end) for start, end in plan_windows(strengths, budget, _STRIDE)]

        lead = self._tokenizer.build_inputs_with_special_tokens([-1]).index(-1)
        input_ids = [self._tokenizer.build_inputs_with_special_tokens(encodings[i][0][s:e]) for i, s, e in windows]
        for batch in self._pack([len(ids) for ids in input_ids]):
            width = len(input_ids[batch[-1]])
            ids = torch.full((len(batch), width), self._tokenizer.pad_token_id, dtype=torch.long)
            mask = torch.zeros((len(batch), width), dtype=torch.long)
            for row, w in enumerate(batch):
                ids[row, : len(input_ids[w])] = torch.tensor(input_ids[w])
                mask[row, : len(input_ids[w])] = 1
            with torch.inference_mode():
                logits = self._model(input_ids=ids.to(self._device), attention_mask=mask.to(self._device)).logits
                conf, pred = logits.float().softmax(-1).max(-1)
            conf_rows, pred_rows = conf.cpu().tolist(), pred.cpu().tolist()

            for row, w in enumerate(batch):
                i, start, end = windows[w]
                for k in range(end - start):
                    context = min(k, end - start - 1 - k)
                    if context > best[i].get(start + k, (-1,))[0]:
                        best[i][start + k] = (
                            context,
                            self._id2label[pred_rows[row][lead + k]],
                            conf_rows[row][lead + k],
                        )

        floors = LABEL_FLOORS if label_floors is None else label_floors
        results: list[list[EntitySpan]] = []
        for i, text in enumerate(texts):
            if not best[i]:
                results.append([])
                continue
            _, offsets, word_ids = encodings[i]
            order = sorted(best[i])
            offs, tags, scs = self._pool_words(
                [offsets[t] for t in order],
                [best[i][t][1] for t in order],
                [best[i][t][2] for t in order],
                [word_ids[t] for t in order],
            )
            spans = [
                EntitySpan(
                    surface_text=text[start:end],
                    label=normalize_label(label),
                    start_offset=start,
                    end_offset=end,
                    score=float(score),
                )
                for start, end, label, score in self._merge(text, offs, tags, scs)
            ]
            results.append([span for span in spans if span.score >= max(threshold, floors.get(span.label, 0.0))])
        return results

    def unload(self) -> None:
        """Release the model."""
        del self._model
        if self._device == "cuda":
            self._torch.cuda.empty_cache()
