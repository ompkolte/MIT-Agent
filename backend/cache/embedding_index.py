from __future__ import annotations

import numpy as np

from backend.cache.similarity import cosine_topk


class EmbeddingIndex:
    """Tiny in-memory index over cache entry embeddings.

    For < ~50K entries a numpy linear scan is faster than FAISS setup. If the cache ever
    grows past that, swap this class for a FAISS or Qdrant-backed equivalent — the
    interface (add, search, remove) is stable.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self._keys: list[str] = []
        self._matrix: np.ndarray = np.zeros((0, dimension), dtype=np.float32)

    def __len__(self) -> int:
        return len(self._keys)

    def add(self, cache_key: str, embedding: np.ndarray) -> None:
        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if vec.shape[0] != self.dimension:
            raise ValueError(
                f"embedding dimension {vec.shape[0]} != index dimension {self.dimension}"
            )
        self._keys.append(cache_key)
        if self._matrix.size == 0:
            self._matrix = vec.reshape(1, -1).copy()
        else:
            self._matrix = np.vstack([self._matrix, vec])

    def remove(self, cache_key: str) -> bool:
        try:
            idx = self._keys.index(cache_key)
        except ValueError:
            return False
        del self._keys[idx]
        self._matrix = np.delete(self._matrix, idx, axis=0)
        return True

    def replace(self, cache_key: str, embedding: np.ndarray) -> None:
        """Update an existing key's vector. Used when an entry is re-stored after refresh."""
        try:
            idx = self._keys.index(cache_key)
        except ValueError:
            self.add(cache_key, embedding)
            return
        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        self._matrix[idx] = vec

    def search(self, query_embedding: np.ndarray, top_k: int = 1) -> list[tuple[str, float]]:
        if self._matrix.size == 0:
            return []
        hits = cosine_topk(query_embedding, self._matrix, top_k=top_k)
        return [(self._keys[i], score) for i, score in hits]

    def clear(self) -> None:
        self._keys = []
        self._matrix = np.zeros((0, self.dimension), dtype=np.float32)

    def keys(self) -> list[str]:
        return list(self._keys)
