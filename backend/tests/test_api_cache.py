"""API-level smoke tests for the semantic cache endpoints."""

from fastapi.testclient import TestClient

from backend.api.main import app


def _post(client, path, body):
    return client.post(path, json={**body, "provider": "mock"})


def test_cache_stats_starts_with_zero_hits_after_clear() -> None:
    client = TestClient(app)
    client.delete("/cache/clear")
    stats = client.get("/cache/stats").json()
    assert stats["total_entries"] == 0
    assert stats["total_hits"] == 0


def test_cache_inspect_returns_list() -> None:
    client = TestClient(app)
    data = client.get("/cache/inspect?limit=5").json()
    assert isinstance(data, list)


def test_chat_response_carries_cache_field() -> None:
    """The response shape must always include the `cache` block, hit or miss."""
    client = TestClient(app)
    client.delete("/cache/clear")
    response = _post(client, "/chat", {"query": "What is MCA eligibility?", "top_k": 3, "run_judge": False})
    assert response.status_code == 200
    data = response.json()
    assert "cache" in data
    assert data["cache"]["hit"] is False  # First call: miss


def test_cache_can_be_disabled_per_request() -> None:
    client = TestClient(app)
    client.delete("/cache/clear")
    response = _post(
        client, "/chat", {"query": "Hello", "top_k": 3, "run_judge": False, "use_cache": False}
    )
    assert response.status_code == 200
    # use_cache=False means no entry should be written
    stats = client.get("/cache/stats").json()
    assert stats["total_entries"] == 0
