from typing import Literal

import numpy as np
import torch


def normalize(v: np.ndarray) -> np.ndarray:
    """L2-Normalize vectors to unit length along the last axis."""
    # axis=-1 ensures we normalize the 1024 features, not the batch
    # keepdims=True makes division easy regardless of input shape
    norm = np.linalg.norm(v, axis=-1, keepdims=True)

    # Use a tiny epsilon instead of 0 to avoid DivisionByZero edge cases
    return v / np.where(norm > 1e-12, norm, 1.0)


def pool_np(embeddings: np.ndarray) -> np.ndarray:
    """Pool a batch of embeddings using average pooling."""
    return np.mean(embeddings, axis=0)


def pool_pt(
    hidden_states: torch.Tensor,
    attention_mask: torch.Tensor,
    method: Literal["avg", "cls"] = "avg",
) -> torch.Tensor:
    """Pooling function for a batch of hidden states."""
    if method == "avg":
        pooled = torch.sum(
            hidden_states * attention_mask.unsqueeze(-1), dim=1
        ) / torch.sum(attention_mask, dim=1, keepdim=True)
    elif method == "cls":
        pooled = hidden_states[:, 0]
    else:
        raise ValueError(f"Pooling method {method} not supported")
    return pooled
