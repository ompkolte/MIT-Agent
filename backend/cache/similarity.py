from __future__ import annotations

import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for two 1-D vectors. Returns 0.0 if either vector has zero norm."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def cosine_topk(query_vec: np.ndarray, matrix: np.ndarray, top_k: int = 1) -> list[tuple[int, float]]:
    """Return [(index, similarity)] of the top-k rows of `matrix` most similar to query_vec.

    Vectors are NOT renormalized — caller is expected to use already-normalized
    embeddings (bge-small-en-v1.5 always outputs normalized). If norms drift we still get
    a usable ranking; just not the exact cosine value."""
    if matrix.size == 0:
        return []
    query_vec = np.asarray(query_vec, dtype=np.float32)
    if query_vec.ndim == 2 and query_vec.shape[0] == 1:
        query_vec = query_vec[0]
    scores = matrix @ query_vec
    if top_k >= len(scores):
        order = np.argsort(scores)[::-1]
    else:
        order = np.argpartition(scores, -top_k)[-top_k:]
        order = order[np.argsort(scores[order])[::-1]]
    return [(int(i), float(scores[i])) for i in order]
