import numpy as np

from backend.cache.similarity import cosine_similarity, cosine_topk


def test_cosine_similarity_identity() -> None:
    v = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_opposite() -> None:
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([-1.0, 0.0], dtype=np.float32)
    assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-6


def test_cosine_similarity_orthogonal() -> None:
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert abs(cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_zero_vector() -> None:
    a = np.zeros(4, dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == 0.0


def test_cosine_topk_returns_sorted_by_similarity() -> None:
    matrix = np.eye(4, dtype=np.float32)
    q = np.array([1.0, 0.1, 0.0, 0.0], dtype=np.float32)
    q /= np.linalg.norm(q)
    hits = cosine_topk(q, matrix, top_k=2)
    assert hits[0][0] == 0
    assert hits[1][0] == 1
    assert hits[0][1] > hits[1][1]


def test_cosine_topk_empty_matrix() -> None:
    assert cosine_topk(np.array([1.0, 0.0]), np.zeros((0, 2), dtype=np.float32)) == []
