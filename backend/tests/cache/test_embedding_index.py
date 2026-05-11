import numpy as np
import pytest

from backend.cache.embedding_index import EmbeddingIndex


def _unit(arr):
    arr = np.asarray(arr, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def test_index_starts_empty() -> None:
    idx = EmbeddingIndex(dimension=4)
    assert len(idx) == 0
    assert idx.search(_unit([1, 0, 0, 0])) == []


def test_add_and_search() -> None:
    idx = EmbeddingIndex(dimension=4)
    idx.add("a", _unit([1, 0, 0, 0]))
    idx.add("b", _unit([0, 1, 0, 0]))
    idx.add("c", _unit([1, 0.1, 0, 0]))
    hits = idx.search(_unit([1, 0.05, 0, 0]), top_k=3)
    assert hits[0][0] in {"a", "c"}
    assert len(hits) == 3


def test_add_rejects_wrong_dimension() -> None:
    idx = EmbeddingIndex(dimension=4)
    with pytest.raises(ValueError):
        idx.add("a", _unit([1, 0]))


def test_remove() -> None:
    idx = EmbeddingIndex(dimension=4)
    idx.add("a", _unit([1, 0, 0, 0]))
    idx.add("b", _unit([0, 1, 0, 0]))
    assert idx.remove("a") is True
    assert len(idx) == 1
    assert idx.search(_unit([1, 0, 0, 0]))[0][0] == "b"


def test_replace() -> None:
    idx = EmbeddingIndex(dimension=4)
    idx.add("a", _unit([1, 0, 0, 0]))
    idx.replace("a", _unit([0, 1, 0, 0]))
    hits = idx.search(_unit([0, 1, 0, 0]))
    assert hits[0][0] == "a"
    assert hits[0][1] > 0.99


def test_replace_inserts_if_missing() -> None:
    idx = EmbeddingIndex(dimension=4)
    idx.replace("a", _unit([1, 0, 0, 0]))
    assert len(idx) == 1


def test_clear() -> None:
    idx = EmbeddingIndex(dimension=4)
    idx.add("a", _unit([1, 0, 0, 0]))
    idx.clear()
    assert len(idx) == 0
    assert idx.search(_unit([1, 0, 0, 0])) == []
