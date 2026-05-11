from pathlib import Path

import numpy as np

from backend.cache.semantic_cache import SemanticCache


class _DeterministicEmbedder:
    """Simulates BGE-small: hashes text → seeded random unit vector. Same input gives
    same vector; near-identical inputs give near-identical vectors (for test purposes
    we just give exact matches when texts match exactly)."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed_query(self, text: str) -> np.ndarray:
        import hashlib

        seed = int(hashlib.md5(text.lower().strip().encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(self.dimension).astype(np.float32)
        return v / np.linalg.norm(v)


def test_miss_when_cache_empty(tmp_path: Path) -> None:
    cache = SemanticCache(embedder=_DeterministicEmbedder(), db_path=tmp_path / "c.db")
    assert cache.lookup("hello") is None
    assert cache.metrics.misses == 1


def test_store_then_hit_on_same_query(tmp_path: Path, good_answer) -> None:
    cache = SemanticCache(embedder=_DeterministicEmbedder(), db_path=tmp_path / "c.db")
    stored, reason = cache.store_answer("What is MCA eligibility?", good_answer, primary_section_type="eligibility")
    assert stored is True
    assert reason is None
    hit = cache.lookup("What is MCA eligibility?")
    assert hit is not None
    assert hit.entry.answer.answer == good_answer.answer
    assert hit.similarity > 0.99


def test_miss_when_below_similarity_threshold(tmp_path: Path, good_answer) -> None:
    cache = SemanticCache(
        embedder=_DeterministicEmbedder(),
        db_path=tmp_path / "c.db",
        similarity_threshold=0.95,
    )
    cache.store_answer("What is MCA eligibility?", good_answer, primary_section_type="eligibility")
    # Different text → fake embedder gives random unrelated vector → similarity well below 0.95
    hit = cache.lookup("Tell me about hostel facilities")
    assert hit is None


def test_abstention_is_not_stored(tmp_path: Path, abstained_answer) -> None:
    cache = SemanticCache(embedder=_DeterministicEmbedder(), db_path=tmp_path / "c.db")
    stored, reason = cache.store_answer("anything", abstained_answer)
    assert stored is False
    assert reason == "abstained"


def test_hit_count_increments_on_lookup(tmp_path: Path, good_answer) -> None:
    cache = SemanticCache(embedder=_DeterministicEmbedder(), db_path=tmp_path / "c.db")
    cache.store_answer("Q", good_answer, primary_section_type="eligibility")
    cache.lookup("Q")
    cache.lookup("Q")
    entries = cache.all_entries()
    assert entries[0].hit_count == 2


def test_stats_reports_section_distribution(tmp_path: Path, good_answer) -> None:
    cache = SemanticCache(embedder=_DeterministicEmbedder(), db_path=tmp_path / "c.db")
    cache.store_answer("q1", good_answer, primary_section_type="eligibility")
    cache.store_answer("q2", good_answer, primary_section_type="fees")
    cache.store_answer("q3", good_answer, primary_section_type="fees")
    stats = cache.stats()
    assert stats.total_entries == 3
    assert stats.section_type_distribution == {"eligibility": 1, "fees": 2}


def test_clear(tmp_path: Path, good_answer) -> None:
    cache = SemanticCache(embedder=_DeterministicEmbedder(), db_path=tmp_path / "c.db")
    cache.store_answer("q1", good_answer, primary_section_type="eligibility")
    cleared = cache.clear()
    assert cleared == 1
    assert cache.stats().total_entries == 0
