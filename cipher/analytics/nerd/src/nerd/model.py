"""Transformers token-classification wrapper producing `EntitySpan`s."""

from loguru import logger

from cipher.schemas.common import ModelDevice
from nerd.labels import normalize_label
from nerd.schemas import EntitySpan


class NerdModel:
    """A fine-tuned token-classification NER model behind a HF `ner` pipeline."""

    def __init__(
        self,
        model_dir: str,
        device: ModelDevice = ModelDevice.CPU,
        aggregation_strategy: str = "first",
    ):
        from transformers import (
            AutoModelForTokenClassification,
            AutoTokenizer,
            pipeline,
        )

        tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
        model = AutoModelForTokenClassification.from_pretrained(model_dir)
        self._pipeline = pipeline(
            "ner",
            model=model,
            tokenizer=tokenizer,
            device=0 if device == ModelDevice.CUDA else -1,
            aggregation_strategy=aggregation_strategy,
        )
        logger.info(
            f"✅ nerd model loaded from {model_dir} "
            f"({'cuda' if device == ModelDevice.CUDA else 'cpu'}, agg={aggregation_strategy})."
        )

    def infer(self, text: str, threshold: float = 0.5) -> list[EntitySpan]:
        """Predict entity spans, keeping aggregated groups at/above `threshold`."""
        if not text.strip():
            return []
        return [
            EntitySpan(
                surface_text=g["word"],
                label=normalize_label(g.get("entity_group") or g.get("entity", "")),
                start_offset=int(g["start"]),
                end_offset=int(g["end"]),
                score=float(g["score"]),
            )
            for g in self._pipeline(text)
            if float(g["score"]) >= threshold and g.get("start") is not None
        ]

    def unload(self) -> None:
        """Release the underlying pipeline."""
        del self._pipeline
