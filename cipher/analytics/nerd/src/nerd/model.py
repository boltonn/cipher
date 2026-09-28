"""Transformers token-classification wrapper producing `EntitySpan`s.

Decoding is offset-based (not the HF ``pipeline("ner")`` word-aggregation): the
model is run over sub-word tokens, predictions are argmax'd per token, and BIO
runs are merged back to character spans via the tokenizer's offset mapping.
This keeps it correct for scripts without whitespace word boundaries (Chinese,
Japanese) and for documents longer than the encoder's 512-token window, which
are processed as overlapping strides.
"""

from __future__ import annotations

import re

from loguru import logger

from cipher.schemas._base.common import ModelDevice
from nerd.labels import normalize_label
from nerd.schemas import EntitySpan

_MAX_TOKENS = 512
_STRIDE = 64

# URLs were never a training label, so the model free-associates on their path
# segments (query strings, %-encoded words) and emits junk location/org spans.
# Blanking them out char-for-char keeps every other span's offset valid.
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def _mask_urls(text: str) -> str:
    return _URL_RE.sub(lambda m: " " * len(m.group()), text)


class NerdModel:
    """A fine-tuned token-classification NER model with offset-based span decoding."""

    def __init__(
        self,
        model_dir: str,
        device: ModelDevice = ModelDevice.CPU,
        aggregation_strategy: str = "first",  # accepted for config compatibility; unused
    ):
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        self._torch = torch
        self._device = "cuda" if device == ModelDevice.CUDA else "cpu"
        self._tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
        model = AutoModelForTokenClassification.from_pretrained(model_dir)
        if self._device == "cuda":
            model = model.half()
        self._model = model.to(self._device).eval()
        self._id2label: dict[int, str] = self._model.config.id2label
        logger.info(
            f"✅ nerd model loaded from {model_dir} ({self._device}, "
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
            continues = cur_label == label and not (prefix == "B" and has_gap)
            if continues:
                cur_end = b
                cur_scores.append(sc)
            else:
                flush()
                cur_label, cur_start, cur_end, cur_scores = label, a, b, [sc]
        flush()
        return spans

    def infer(self, text: str, threshold: float = 0.5) -> list[EntitySpan]:
        """Predict entity spans over `text`, keeping spans scoring at/above `threshold`."""
        if not text or not text.strip():
            return []

        torch = self._torch
        masked = _mask_urls(text)  # same length as `text` -- offsets below still index the original
        enc = self._tokenizer(
            masked,
            return_offsets_mapping=True,
            return_tensors="pt",
            truncation=True,
            max_length=_MAX_TOKENS,
            stride=_STRIDE,
            return_overflowing_tokens=True,
            padding=True,
        )
        offset_windows = enc.pop("offset_mapping")
        enc.pop("overflow_to_sample_mapping", None)
        model_inputs = {k: v.to(self._device) for k, v in enc.items()}

        with torch.inference_mode():
            logits = self._model(**model_inputs).logits
            probs = logits.softmax(-1)
            conf, pred = probs.max(-1)

        merged: dict[tuple[int, int, str], float] = {}
        for w in range(pred.shape[0]):
            offs = [tuple(o) for o in offset_windows[w].tolist()]
            tags = [self._id2label[int(i)] for i in pred[w].tolist()]
            scs = conf[w].tolist()
            for start, end, label, score in self._merge(text, offs, tags, scs):
                key = (start, end, label)
                if score > merged.get(key, 0.0):
                    merged[key] = score

        out = [
            EntitySpan(
                surface_text=text[start:end],
                label=normalize_label(label),
                start_offset=start,
                end_offset=end,
                score=float(score),
            )
            for (start, end, label), score in sorted(merged.items())
            if score >= threshold
        ]
        return out

    def unload(self) -> None:
        """Release the model."""
        del self._model
        if self._device == "cuda":
            self._torch.cuda.empty_cache()
