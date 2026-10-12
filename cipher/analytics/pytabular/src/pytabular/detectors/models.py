"""Model detectors: GLiNER2.5 zero-shot classification and nerd whole-cell NER.

Both take a plain callable, so the model can run in-process (`from_model_dir`) or
behind its analytic's HTTP API (`from_url`) without pytabular importing torch.
"""

from collections.abc import Callable

import httpx

from cipher.schemas._base.common import ModelDevice
from pytabular.detectors import ColumnScores, TableContext
from pytabular.fields import field_types
from pytabular.profile import ColumnSample

ClassifyFn = Callable[[list[str], dict[str, str]], list[dict[str, float]]]
NerFn = Callable[[list[str]], list[list[dict]]]

_NER_LABEL_TO_FIELD = {
    "person": "person.full_name",
    "person.name": "person.full_name",
    "organization": "organization.name",
    "organization.name": "organization.name",
    "location": "location.place_name",
    "location.name": "location.place_name",
    "location.address": "location.address",
    "address": "location.address",
}


def column_text(column: ColumnSample, *, has_header: bool, n: int = 12) -> str:
    """`Column header: X. Values: a; b; c` -- the text a model classifies."""
    values = "; ".join(column.preview(n))
    return f"Column header: {column.header}. Values: {values}" if has_header else f"Column values: {values}"


class GlinerDetector:
    name = "gliner"

    def __init__(self, classify: ClassifyFn):
        self._classify = classify
        self._labels = {f.label: f.description for f in field_types().values() if f.id != "other"}
        self._label_to_field = {f.label: f.id for f in field_types().values()}

    @classmethod
    def from_model_dir(cls, model_dir: str, *, device: ModelDevice = ModelDevice.CPU) -> "GlinerDetector":
        """In-process GLiNER2.5 (needs the `gliner` extra)."""
        from pygliner.model import GlinerModel

        model = GlinerModel(model_dir, device=device)
        return cls(lambda texts, labels: model.classify(texts, labels))

    @classmethod
    def from_url(cls, url: str, *, timeout: float = 120.0) -> "GlinerDetector":
        """Pygliner's `POST /classify`."""

        def classify(texts: list[str], labels: dict[str, str]) -> list[dict[str, float]]:
            response = httpx.post(
                f"{url.rstrip('/')}/classify", json={"texts": texts, "labels": labels}, timeout=timeout
            )
            response.raise_for_status()
            return response.json()

        return cls(classify)

    def score(self, columns: list[ColumnSample], *, context: TableContext) -> list[ColumnScores]:
        """Zero-shot label scores for each column's header + sample values."""
        live = [c for c in columns if c.values]
        results = (
            self._classify([column_text(c, has_header=context.has_header) for c in live], self._labels) if live else []
        )
        by_index = {c.index: r for c, r in zip(live, results, strict=True)}
        return [
            ColumnScores(
                scores={
                    self._label_to_field[k]: v
                    for k, v in by_index.get(c.index, {}).items()
                    if k in self._label_to_field
                }
            )
            for c in columns
        ]


class NerdDetector:
    name = "nerd"

    def __init__(self, infer: NerFn, *, cells: int = 30):
        self._infer = infer
        self._cells = cells

    @classmethod
    def from_model_dir(
        cls, model_dir: str, *, device: ModelDevice = ModelDevice.CPU, threshold: float = 0.5
    ) -> "NerdDetector":
        """In-process nerd (needs the `nerd` extra)."""
        from nerd.model import NerdModel

        model = NerdModel(model_dir, device=device)
        return cls(lambda texts: [[s.model_dump() for s in spans] for spans in model.infer_batch(texts, threshold)])

    @classmethod
    def from_url(cls, url: str, *, threshold: float = 0.5, timeout: float = 120.0) -> "NerdDetector":
        """Nerd's `POST /infer/batch`."""

        def infer(texts: list[str]) -> list[list[dict]]:
            body = {"texts": texts, "threshold": threshold}
            response = httpx.post(f"{url.rstrip('/')}/infer/batch", json=body, timeout=timeout)
            response.raise_for_status()
            return response.json()

        return cls(infer)

    def score(self, columns: list[ColumnSample], *, context: TableContext) -> list[ColumnScores]:
        """Share of cells that are one whole person / organization / location span."""
        cells = [(c.index, v) for c in columns for v in c.distinct[: self._cells]]
        if not cells:
            return [ColumnScores() for _ in columns]
        spans = self._infer([v for _, v in cells])
        hits: dict[int, dict[str, int]] = {}
        totals: dict[int, int] = {}
        for (index, value), found in zip(cells, spans, strict=True):
            totals[index] = totals.get(index, 0) + 1
            for span in found:
                start, end = (
                    span.get("start_offset", span.get("startOffset", 0)),
                    span.get("end_offset", span.get("endOffset", 0)),
                )
                field_id = _NER_LABEL_TO_FIELD.get(str(span.get("label", "")).lower())
                if field_id and end - start >= 0.9 * len(value):
                    hits.setdefault(index, {})[field_id] = hits.get(index, {}).get(field_id, 0) + 1
                    break
        return [
            ColumnScores(scores={k: n / totals[c.index] for k, n in hits.get(c.index, {}).items()})
            if c.index in totals
            else ColumnScores()
            for c in columns
        ]
