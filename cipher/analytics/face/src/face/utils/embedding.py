import numpy as np


def normalize(embedding: list[float]) -> list[float]:
    """Normalize an embedding to unit length."""
    arr = np.array(embedding, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm == 0:
        return embedding
    normalized = arr / norm
    return normalized.tolist()
