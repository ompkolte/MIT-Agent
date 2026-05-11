from __future__ import annotations

import time

from backend.cache.cache_store import CacheStore
from backend.cache.embedding_index import EmbeddingIndex
from backend.cache.freshness import ttl_for
from backend.cache.models.cache_entry import CACHE_VERSION


def invalidate_by_version(store: CacheStore, index: EmbeddingIndex) -> int:
    """Drop entries that don't match the current CACHE_VERSION. Called at startup so
    schema or embedding-model bumps automatically purge stale entries."""
    affected: list[str] = []
    for entry in store.all_entries():
        if entry.cache_version != CACHE_VERSION:
            affected.append(entry.cache_key)
    for key in affected:
        store.delete(key)
        index.remove(key)
    return len(affected)


def invalidate_stale(store: CacheStore, index: EmbeddingIndex, now: float | None = None) -> int:
    """Drop entries past their TTL. Caller usually runs this on a schedule or on startup."""
    cutoff_now = now if now is not None else time.time()
    affected: list[str] = []
    for entry in store.all_entries():
        if (cutoff_now - entry.created_at) > ttl_for(entry.primary_section_type):
            affected.append(entry.cache_key)
    for key in affected:
        store.delete(key)
        index.remove(key)
    return len(affected)


def invalidate_by_section_type(
    store: CacheStore, index: EmbeddingIndex, section_type: str
) -> int:
    """Clear all entries with the given section_type — used when the underlying corpus
    for a topic has been re-ingested (e.g. fees updated)."""
    affected = [e.cache_key for e in store.all_entries() if e.primary_section_type == section_type]
    for key in affected:
        store.delete(key)
        index.remove(key)
    return len(affected)


def invalidate_all(store: CacheStore, index: EmbeddingIndex) -> int:
    affected = store.count()
    store.clear()
    index.clear()
    return affected
