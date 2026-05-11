from pathlib import Path

import numpy as np

from backend.cache.cache_store import CacheStore


def _vec(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(384).astype(np.float32)
    return v / np.linalg.norm(v)


def test_upsert_and_get(tmp_path: Path, good_answer) -> None:
    store = CacheStore(db_path=tmp_path / "cache.db")
    store.upsert(
        cache_key="k1",
        normalized_query="mca eligibility",
        original_query="What is MCA eligibility?",
        answer=good_answer,
        embedding=_vec(1),
        intent="eligibility_query",
        primary_section_type="eligibility",
        primary_page_type="Admissions",
    )
    entry = store.get("k1")
    assert entry is not None
    assert entry.normalized_query == "mca eligibility"
    assert entry.primary_section_type == "eligibility"
    assert entry.answer.answer == good_answer.answer
    assert entry.hit_count == 0


def test_record_hit_increments(tmp_path: Path, good_answer) -> None:
    store = CacheStore(db_path=tmp_path / "cache.db")
    store.upsert("k1", "q", "Q", good_answer, _vec(1), primary_section_type="eligibility")
    store.record_hit("k1")
    store.record_hit("k1")
    assert store.get("k1").hit_count == 2


def test_get_embedding_returns_array(tmp_path: Path, good_answer) -> None:
    store = CacheStore(db_path=tmp_path / "cache.db")
    v = _vec(7)
    store.upsert("k1", "q", "Q", good_answer, v, primary_section_type="eligibility")
    loaded = store.get_embedding("k1")
    assert loaded is not None
    assert loaded.shape == (384,)
    assert np.allclose(loaded, v)


def test_delete_where_by_version(tmp_path: Path, good_answer) -> None:
    store = CacheStore(db_path=tmp_path / "cache.db")
    store.upsert("k1", "q1", "Q1", good_answer, _vec(1), primary_section_type="fees")
    n = store.delete_where(cache_version="bogus-version")
    assert n == 1
    assert store.count() == 0


def test_section_type_distribution(tmp_path: Path, good_answer) -> None:
    store = CacheStore(db_path=tmp_path / "cache.db")
    store.upsert("a", "q", "Q", good_answer, _vec(1), primary_section_type="eligibility")
    store.upsert("b", "q", "Q", good_answer, _vec(2), primary_section_type="fees")
    store.upsert("c", "q", "Q", good_answer, _vec(3), primary_section_type="fees")
    dist = store.section_type_distribution()
    assert dist == {"eligibility": 1, "fees": 2}


def test_clear(tmp_path: Path, good_answer) -> None:
    store = CacheStore(db_path=tmp_path / "cache.db")
    store.upsert("k1", "q", "Q", good_answer, _vec(1), primary_section_type="eligibility")
    cleared = store.clear()
    assert cleared == 1
    assert store.count() == 0
