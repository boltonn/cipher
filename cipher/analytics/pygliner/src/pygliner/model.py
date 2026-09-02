"""GLiNER (entities) and GLiREL (relations) wrappers producing typed spans."""

import re

from loguru import logger

from cipher.schemas._base.common import ModelDevice
from cipher.schemas.graph.ontology import default_ner_labels, default_relation_labels
from pygliner.schemas import EntitySpan, RelationSpan

_TOKEN_RE = re.compile(r"\S+")


class GlinerModel:
    """Zero-shot entity span extraction over a GLiNER checkpoint."""

    def __init__(self, model_dir: str, device: ModelDevice = ModelDevice.CPU):
        from gliner import GLiNER

        self._model = GLiNER.from_pretrained(model_dir)
        self._device = "cuda" if device == ModelDevice.CUDA else "cpu"
        self._model.to(self._device)
        logger.info(f"✅ GLiNER loaded from {model_dir} on {self._device}.")

    def infer(
        self, text: str, labels: list[str] | None = None, threshold: float = 0.5
    ) -> list[EntitySpan]:
        """Predict entity spans for the requested labels."""
        if not text.strip():
            return []
        predictions = self._model.predict_entities(
            text, labels or default_ner_labels(), threshold=threshold
        )
        return [
            EntitySpan(
                surface_text=p["text"],
                label=p["label"],
                start_offset=p["start"],
                end_offset=p["end"],
                score=float(p.get("score", threshold)),
            )
            for p in predictions
        ]

    def unload(self) -> None:
        """Release the underlying model."""
        del self._model


class GlirelModel:
    """Zero-shot relation extraction over a GLiREL checkpoint (optional extra)."""

    def __init__(self, model_dir: str, device: ModelDevice = ModelDevice.CPU):
        try:
            from glirel import GLiREL
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Relation extraction needs the `relations` extra: uv sync --extra relations"
            ) from exc

        self._model = GLiREL.from_pretrained(model_dir)
        self._device = "cuda" if device == ModelDevice.CUDA else "cpu"
        self._model.to(self._device)
        logger.info(f"✅ GLiREL loaded from {model_dir} on {self._device}.")

    def infer(
        self,
        text: str,
        entities: list[EntitySpan],
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ) -> list[RelationSpan]:
        """Predict directed relations between the supplied entity spans."""
        if len(entities) < 2 or not text.strip():
            return []

        tokens, offsets = _tokenize(text)
        ner = []
        for e in entities:
            span = _token_span(offsets, e.start_offset, e.end_offset)
            if span is not None:
                ner.append([span[0], span[1], e.label, e.surface_text])
        if len(ner) < 2:
            return []

        raw = self._model.predict_relations(
            tokens,
            {"glirel_labels": {label: {} for label in (labels or default_relation_labels())}},
            threshold=threshold,
            ner=ner,
            top_k=1,
        )
        return [
            RelationSpan(
                label=r["label"],
                head_text=" ".join(r["head_text"]) if isinstance(r["head_text"], list) else r["head_text"],
                tail_text=" ".join(r["tail_text"]) if isinstance(r["tail_text"], list) else r["tail_text"],
                head_start=offsets[r["head_pos"][0]][0],
                tail_start=offsets[r["tail_pos"][0]][0],
                score=float(r.get("score", threshold)),
            )
            for r in raw
        ]

    def unload(self) -> None:
        """Release the underlying model."""
        del self._model


def _tokenize(text: str) -> tuple[list[str], list[tuple[int, int]]]:
    tokens: list[str] = []
    offsets: list[tuple[int, int]] = []
    for m in _TOKEN_RE.finditer(text):
        tokens.append(m.group(0))
        offsets.append((m.start(), m.end()))
    return tokens, offsets


def _token_span(offsets: list[tuple[int, int]], start: int, end: int) -> tuple[int, int] | None:
    idx = [i for i, (s, e) in enumerate(offsets) if s < end and e > start]
    return (idx[0], idx[-1]) if idx else None
