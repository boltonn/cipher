"""Tag heads: lightweight per-tag classifiers over L2-normalized CLIP image embeddings.

Each head is a logistic-regression probe (one weight vector + bias). All heads are stacked
into a single `[tags, dim]` matrix, so scoring every tag for a batch is one matmul + sigmoid:
~`tags * dim * 4` bytes (100 tags x 512 dims = 200 KB), cheap enough to fuse into the
embedding pass on the GPU, or to run on CPU over embeddings already stored in Postgres.

Saved as `heads.safetensors` (weights, biases, thresholds -- plain tensors, no pickle) plus
`heads.json` (tag names, embedding model, version, training metrics).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from safetensors.numpy import load_file, save_file

if TYPE_CHECKING:
    import torch

WEIGHTS_FILE = "heads.safetensors"
META_FILE = "heads.json"


@dataclass
class TagHeads:
    """A bank of binary tag classifiers sharing one embedding space."""

    tags: list[str]
    weight: np.ndarray  # [T, D] float32
    bias: np.ndarray  # [T] float32
    thresholds: np.ndarray  # [T] decision threshold per tag (max out-of-fold F1)
    embedding_model: str
    version: str
    metrics: dict[str, dict] = field(default_factory=dict)
    _device_tensors: dict = field(default_factory=dict, repr=False)

    @property
    def source_name(self) -> str:
        """How scores from this bank are attributed (a `model` tag source)."""
        return f"setfitcv-heads:{self.version}"

    def select(self, tags: list[str]) -> "TagHeads":
        """A bank with just these tags (unknown tags are ignored)."""
        keep = [i for i, tag in enumerate(self.tags) if tag in set(tags)]
        return TagHeads(
            tags=[self.tags[i] for i in keep],
            weight=self.weight[keep],
            bias=self.bias[keep],
            thresholds=self.thresholds[keep],
            embedding_model=self.embedding_model,
            version=self.version,
            metrics={self.tags[i]: self.metrics.get(self.tags[i], {}) for i in keep},
        )

    def score(self, embeddings: np.ndarray) -> np.ndarray:
        """`[N, T]` probabilities for `[N, D]` normalized embeddings, on CPU."""
        logits = np.asarray(embeddings, dtype=np.float32) @ self.weight.T + self.bias
        return 1.0 / (1.0 + np.exp(-logits))

    def score_tensor(self, embeddings: "torch.Tensor") -> "torch.Tensor":
        """`[N, T]` probabilities for embeddings already on a device -- weights are copied there once."""
        import torch

        key = str(embeddings.device)
        if key not in self._device_tensors:
            self._device_tensors[key] = (
                torch.from_numpy(self.weight).to(embeddings.device),
                torch.from_numpy(self.bias).to(embeddings.device),
            )
        weight, bias = self._device_tensors[key]
        return torch.sigmoid(embeddings.float() @ weight.T + bias)

    def as_dicts(self, scores: np.ndarray, *, min_score: float = 0.0) -> list[dict[str, float]]:
        """`{tag: score}` per row, keeping scores at or above `min_score`."""
        return [
            {tag: float(value) for tag, value in zip(self.tags, row, strict=True) if value >= min_score}
            for row in scores
        ]

    def save(self, directory: Path) -> None:
        """Write the bank (overwrites any bank in `directory`)."""
        directory.mkdir(parents=True, exist_ok=True)
        save_file(
            {"weight": self.weight, "bias": self.bias, "thresholds": self.thresholds},
            str(directory / WEIGHTS_FILE),
        )
        (directory / META_FILE).write_text(
            json.dumps(
                {
                    "tags": self.tags,
                    "embedding_model": self.embedding_model,
                    "version": self.version,
                    "dim": int(self.weight.shape[1]),
                    "metrics": self.metrics,
                },
                indent=2,
            )
        )

    @classmethod
    def load(cls, directory: Path) -> "TagHeads":
        """Read a bank written by `save`."""
        tensors = load_file(str(directory / WEIGHTS_FILE))
        meta = json.loads((directory / META_FILE).read_text())
        return cls(
            tags=meta["tags"],
            weight=tensors["weight"].astype(np.float32),
            bias=tensors["bias"].astype(np.float32),
            thresholds=tensors["thresholds"].astype(np.float32),
            embedding_model=meta["embedding_model"],
            version=meta["version"],
            metrics=meta.get("metrics", {}),
        )
