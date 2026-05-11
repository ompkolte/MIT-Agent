from __future__ import annotations

from pydantic import BaseModel, Field

from backend.answering.models.answer import GroundedAnswer


CACHE_VERSION = "v1"


class CacheEntry(BaseModel):
    """A stored cache entry. The embedding is held separately in the in-memory index;
    this schema is what gets returned to API callers."""

    cache_key: str
    normalized_query: str
    original_query: str
    answer: GroundedAnswer
    grounding_confidence: float
    hallucination_risk: float
    intent: str | None = None
    primary_section_type: str | None = None
    primary_page_type: str | None = None
    cache_version: str = CACHE_VERSION
    created_at: float
    last_used_at: float
    hit_count: int = 0


class CacheHit(BaseModel):
    """Wrapper returned by the router when a cache lookup succeeds."""

    entry: CacheEntry
    similarity: float
    latency_ms: float = 0.0


class CacheStats(BaseModel):
    total_entries: int = 0
    total_hits: int = 0
    total_misses: int = 0
    total_evictions: int = 0
    hit_rate: float = 0.0
    avg_similarity_at_hit: float = 0.0
    avg_latency_saved_ms: float = 0.0
    bytes_on_disk: int = 0
    section_type_distribution: dict[str, int] = Field(default_factory=dict)
