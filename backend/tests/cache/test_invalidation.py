import time
from pathlib import Path

import numpy as np

from backend.cache.cache_store import CacheStore
from backend.cache.embedding_index import EmbeddingIndex
from backend.cache.freshness import DAY
from backend.cache.invalidation import (
    invalidate_all,
    invalidate_by_section_type,
    invalidate_by_version,
    invalidate_stale,
)


def _vec(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(384).astype(np.float32)
    return v / np.linalg.norm(v)


def _populate(tmp_path: Path, good_answer):
    store = CacheStore(db_path=tmp_path / "cache.db")
    index = EmbeddingIndex(dimension=384)
    for i, section_type in enumerate(["eligibility", "fees", "events", "fees"]):
        key = f"k{i}"
        v = _vec(i)
        store.upsert(key, "q", "Q", good_answer, v, primary_section_type=section_type)
        index.add(key, v)
    return store, index


def test_invalidate_by_version_drops_mismatched(tmp_path: Path, good_answer) -> None:
    store, index = _populate(tmp_path, good_answer)
    # Manually bump one entry's version to simulate an old schema
    store._conn.execute("UPDATE cache_entries SET cache_version='old' WHERE cache_key='k0'")
    removed = invalidate_by_version(store, index)
    assert removed == 1
    assert store.get("k0") is None


def test_invalidate_stale_uses_section_ttl(tmp_path: Path, good_answer) -> None:
    store, index = _populate(tmp_path, good_answer)
    # Make 'events' entry 10 days old (TTL is 3d so it should be evicted)
    store._conn.execute(
        "UPDATE cache_entries SET created_at = ? WHERE primary_section_type='events'",
        (time.time() - 10 * DAY,),
    )
    removed = invalidate_stale(store, index)
    assert removed == 1


def test_invalidate_by_section_type(tmp_path: Path, good_answer) -> None:
    store, index = _populate(tmp_path, good_answer)
    removed = invalidate_by_section_type(store, index, "fees")
    assert removed == 2
    assert all(e.primary_section_type != "fees" for e in store.all_entries())


def test_invalidate_all(tmp_path: Path, good_answer) -> None:
    store, index = _populate(tmp_path, good_answer)
    removed = invalidate_all(store, index)
    assert removed == 4
    assert store.count() == 0
    assert len(index) == 0
