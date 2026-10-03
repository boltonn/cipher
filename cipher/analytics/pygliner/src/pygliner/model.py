"""GLiNER2.5 wrapper producing typed entity and relation spans, and zero-shot text labels.

One boundary checkpoint serves every task: entities via the extractor's
long-text API, entities + relations jointly via `JointIE` with a schema whose
relation endpoints are typed from the ontology, and `classify` scoring whole
texts against described labels. Loads from a local directory
with no hub access (the checkpoint bundles its encoder config and tokenizer).
"""

from loguru import logger

from cipher.schemas._base.common import ModelDevice
from cipher.schemas.graph.ontology import (
    NER_LABEL_TO_TYPE,
    RELATION_LABEL_TO_TYPE,
    RELATIONSHIPS,
    default_ner_labels,
    default_relation_labels,
)
from pygliner.schemas import EntitySpan, RelationSpan

_CHUNK_SIZE = 384
_CHUNK_OVERLAP = 64
# `classify` windows texts by characters first: the extractor chunks by words, so text with few
# breaks (base64, URLs, CJK) made one 384-word chunk 12k+ tokens and ~19 GB of attention.
_CLASSIFY_WINDOW_CHARS = 2_000
_CLASSIFY_WINDOW_OVERLAP = 200
# Greedy matches beam's relations on real data (749 vs 748, full overlap) at ~6x the speed;
# beam's Python search dominates runtime (entities alone are ~0.07s/file on GPU).


class GlinerModel:
    """Zero-shot entity and relation extraction over a GLiNER2.5 checkpoint."""

    def __init__(self, model_dir: str, device: ModelDevice = ModelDevice.CPU):
        from gliner2 import AutoExtractor
        from gliner2.joint_ie import JointIE

        self._device = "cuda" if device == ModelDevice.CUDA else "cpu"
        self._model = AutoExtractor.from_pretrained(model_dir, local_files_only=True)
        self._joint = JointIE(self._model, device=self._device)
        self._schemas: dict[tuple[tuple[str, ...], tuple[str, ...]], object] = {}
        logger.info(f"✅ GLiNER2.5 loaded from {model_dir} on {self._device}.")

    def infer(self, text: str, labels: list[str] | None = None, threshold: float = 0.65) -> list[EntitySpan]:
        """Predict entity spans for the requested labels."""
        if not text.strip():
            return []
        result = self._model.extract_entities_long(
            text,
            labels or default_ner_labels(),
            threshold=threshold,
            chunk_size=_CHUNK_SIZE,
            chunk_overlap=_CHUNK_OVERLAP,
            include_spans=True,
            include_confidence=True,
        )
        return [
            EntitySpan(
                surface_text=e["text"],
                label=label,
                start_offset=e["start"],
                end_offset=e["end"],
                score=float(e.get("confidence", threshold)),
            )
            for label, found in result["entities"].items()
            for e in found
        ]

    def extract(
        self,
        text: str,
        labels: list[str] | None = None,
        relation_labels: list[str] | None = None,
        threshold: float = 0.65,
    ) -> tuple[list[EntitySpan], list[RelationSpan]]:
        """Jointly predict entity spans and the typed relations between them."""
        if not text.strip():
            return [], []
        from gliner2.joint_ie import JointIEConfig

        schema = self._schema(
            labels=tuple(labels or default_ner_labels()),
            relation_labels=tuple(relation_labels or default_relation_labels()),
        )
        result = self._joint.extract_long(
            text,
            schema,
            config=JointIEConfig(optimizer="greedy", entity_threshold=threshold),
            chunk_size=_CHUNK_SIZE,
            chunk_overlap=_CHUNK_OVERLAP,
        )
        entities = [
            EntitySpan(
                surface_text=e.text,
                label=e.type,
                start_offset=e.start,
                end_offset=e.end,
                score=float(e.confidence if e.confidence is not None else threshold),
            )
            for e in result.entities
        ]
        relations = []
        for r in result.relations:
            score = float(r.confidence if r.confidence is not None else threshold)
            if score < threshold:
                continue
            head, tail = result.entity(r.head), result.entity(r.tail)
            relations.append(
                RelationSpan(
                    label=r.type,
                    head_text=head.text,
                    tail_text=tail.text,
                    head_start=head.start,
                    tail_start=tail.start,
                    score=score,
                )
            )
        return entities, relations

    def classify(self, texts: list[str], labels: dict[str, str], batch_size: int = 32) -> list[dict[str, float]]:
        """Score each text against every label (name -> description), labels judged independently.

        A long text is scored per character window; a label's score is its highest window, so
        one relevant passage is enough however much boilerplate surrounds it.
        """
        import torch

        windows, owners = [], []
        step = _CLASSIFY_WINDOW_CHARS - _CLASSIFY_WINDOW_OVERLAP
        for index, text in enumerate(texts):
            text = text if text.strip() else " "
            for start in range(0, max(len(text) - _CLASSIFY_WINDOW_OVERLAP, 1), step):
                windows.append(text[start : start + _CLASSIFY_WINDOW_CHARS])
                owners.append(index)

        schema = self._model.create_schema().classification("label", labels, multi_label=True, cls_threshold=0.0)
        with torch.inference_mode(), torch.autocast(self._device, dtype=torch.float16, enabled=self._device == "cuda"):
            results = self._model.batch_extract_long(
                windows,
                schema,
                batch_size=batch_size,
                include_confidence=True,
                chunk_size=_CHUNK_SIZE,
                chunk_overlap=_CHUNK_OVERLAP,
            )
        scores = [dict.fromkeys(labels, 0.0) for _ in texts]
        for owner, result in zip(owners, results, strict=True):
            for match in result.get("label") or []:
                scores[owner][match["label"]] = max(scores[owner][match["label"]], float(match["confidence"]))
        return scores

    def _schema(self, *, labels: tuple[str, ...], relation_labels: tuple[str, ...]):
        """Compiled JointIE schema with each relation's head/tail restricted to ontology-permitted labels.

        Compiled here rather than by `JointIE`, whose own compile cache is keyed on
        the schema's `repr` (a memory address) and can return a stale schema.
        """
        from gliner2.joint_ie import compile_schema

        key = (labels, relation_labels)
        if key not in self._schemas:
            schema = self._joint.create_schema().entities(list(labels))
            for relation_label in relation_labels:
                spec = RELATIONSHIPS.get(RELATION_LABEL_TO_TYPE.get(relation_label))
                if spec is None:
                    continue
                heads = [label for label in labels if NER_LABEL_TO_TYPE.get(label) in spec.allowed_src]
                tails = [label for label in labels if NER_LABEL_TO_TYPE.get(label) in spec.allowed_dst]
                if heads and tails:
                    schema.relation(
                        relation_label,
                        heads,
                        tails,
                        spec.description,
                        directed=spec.directed,
                    )
            self._schemas[key] = compile_schema(schema)
        return self._schemas[key]

    def unload(self) -> None:
        """Release the underlying model."""
        del self._joint
        del self._model
