from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Protocol

import numpy as np

from backend.answering.models.answer import GroundedAnswer
from backend.cache.cache_metrics import CacheMetrics
from backend.cache.cache_store import CacheStore
from backend.cache.cache_validator import is_cacheable, is_hit_still_valid
from backend.cache.embedding_index import EmbeddingIndex
from backend.cache.freshness import is_fresh, staleness_reason
from backend.cache.invalidation import invalidate_by_version
from backend.cache.models.cache_entry import CacheEntry, CacheHit


# Lowered from 0.92 → 0.88 (Phase 6.5 Fix C) so small paraphrases like
# "what clubs are present in mitaoe" and "what are the clubs present in mitaoe" — which
# bge-small embeds ~0.88-0.92 similar — share the same cache entry instead of producing
# different retrievals and divergent answers.
DEFAULT_SIMILARITY_THRESHOLD = 0.88


class _EmbedderLike(Protocol):
    def embed_query(self, text: str) -> np.ndarray:  # pragma: no cover - protocol
        ...


def _normalize(query: str) -> str:
    """Cheap normalization for the cache_key: lowercase + collapse whitespace + strip
    trailing punctuation. The semantic match relies on the embedding; this is just for
    de-duplication on identical strings."""
    if not query:
        return ""
    s = " ".join(query.lower().split())
    return s.rstrip("?!.")


def _cache_key(query: str) -> str:
    return hashlib.sha1(_normalize(query).encode("utf-8")).hexdigest()


class SemanticCache:
    """Front-of-RAG semantic cache. Wraps a CacheStore for persistence and an
    EmbeddingIndex for fast in-memory similarity lookup."""

    def __init__(
        self,
        embedder: _EmbedderLike,
        db_path: Path | str = Path("datasets/semantic_cache.db"),
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        dimension: int = 384,
    ) -> None:
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.store = CacheStore(db_path=db_path)
        self.index = EmbeddingIndex(dimension=dimension)
        self.metrics = CacheMetrics()
        self._load_index()
        evicted = invalidate_by_version(self.store, self.index)
        if evicted:
            self.metrics.record_eviction(evicted)

    def _load_index(self) -> None:
        for key, vec in self.store.all_embeddings():
            self.index.add(key, vec)

    def lookup(self, query: str) -> CacheHit | None:
        """Return a CacheHit if a sufficiently similar, fresh, still-valid entry exists.
        Otherwise return None and record a miss in metrics."""
        start = time.perf_counter()
        if len(self.index) == 0 or not query:
            self.metrics.record_miss()
            return None
        query_vec = np.asarray(self.embedder.embed_query(query), dtype=np.float32)
        results = self.index.search(query_vec, top_k=1)
        if not results:
            self.metrics.record_miss()
            return None
        cache_key, similarity = results[0]
        if similarity < self.similarity_threshold:
            self.metrics.record_miss()
            return None
        entry = self.store.get(cache_key)
        if entry is None:
            # Index drift — embedding present but row missing. Drop from index and miss.
            self.index.remove(cache_key)
            self.metrics.record_miss()
            return None
        if not is_fresh(entry):
            # Don't return a stale entry. Evict it now so it stops blocking newer answers.
            self.metrics.record_stale_hit()
            self.metrics.record_eviction(1)
            self.store.delete(cache_key)
            self.index.remove(cache_key)
            self.metrics.record_miss()
            return None
        ok, reason = is_hit_still_valid(entry.answer)
        if not ok:
            self.metrics.record_miss()
            return None
        self.store.record_hit(cache_key)
        latency_ms = (time.perf_counter() - start) * 1000.0
        self.metrics.record_hit(similarity=similarity, latency_saved_ms=0.0)
        return CacheHit(entry=entry, similarity=round(similarity, 4), latency_ms=round(latency_ms, 2))

    def store_answer(
        self,
        query: str,
        answer: GroundedAnswer,
        intent: str | None = None,
        primary_section_type: str | None = None,
        primary_page_type: str | None = None,
    ) -> tuple[bool, str | None]:
        """Embed the query and store if the answer is eligible. Returns (stored, reason).
        On reject, `reason` explains why the answer wasn't cacheable."""
        eligible, why = is_cacheable(answer)
        if not eligible:
            return False, why
        normalized = _normalize(query)
        key = _cache_key(query)
        embedding = np.asarray(self.embedder.embed_query(query), dtype=np.float32)
        self.store.upsert(
            cache_key=key,
            normalized_query=normalized,
            original_query=query,
            answer=answer,
            embedding=embedding,
            intent=intent,
            primary_section_type=primary_section_type,
            primary_page_type=primary_page_type,
        )
        self.index.replace(key, embedding)
        return True, None

    def stats(self):
        snapshot = self.metrics.snapshot(
            total_entries=self.store.count(),
            section_type_distribution=self.store.section_type_distribution(),
        )
        return snapshot

    def all_entries(self) -> list[CacheEntry]:
        return self.store.all_entries()

    def clear(self) -> int:
        n = self.store.count()
        self.store.clear()
        self.index.clear()
        return n
