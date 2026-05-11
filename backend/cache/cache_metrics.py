from __future__ import annotations

from backend.cache.models.cache_entry import CacheStats


class CacheMetrics:
    """In-memory rolling counters. Persisted state lives in the SQLite hit_count column;
    this class is for runtime/observability."""

    def __init__(self) -> None:
        self.hits: int = 0
        self.misses: int = 0
        self.evictions: int = 0
        self.stale_hits: int = 0
        self.similarities_at_hit: list[float] = []
        self.latency_saved_ms: list[float] = []

    def record_hit(self, similarity: float, latency_saved_ms: float = 0.0) -> None:
        self.hits += 1
        self.similarities_at_hit.append(similarity)
        if latency_saved_ms > 0:
            self.latency_saved_ms.append(latency_saved_ms)

    def record_miss(self) -> None:
        self.misses += 1

    def record_eviction(self, count: int = 1) -> None:
        self.evictions += count

    def record_stale_hit(self) -> None:
        self.stale_hits += 1

    def reset(self) -> None:
        self.__init__()

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def snapshot(
        self,
        total_entries: int = 0,
        bytes_on_disk: int = 0,
        section_type_distribution: dict[str, int] | None = None,
    ) -> CacheStats:
        avg_sim = (
            sum(self.similarities_at_hit) / len(self.similarities_at_hit)
            if self.similarities_at_hit
            else 0.0
        )
        avg_lat = (
            sum(self.latency_saved_ms) / len(self.latency_saved_ms)
            if self.latency_saved_ms
            else 0.0
        )
        return CacheStats(
            total_entries=total_entries,
            total_hits=self.hits,
            total_misses=self.misses,
            total_evictions=self.evictions,
            hit_rate=round(self.hit_rate, 4),
            avg_similarity_at_hit=round(avg_sim, 4),
            avg_latency_saved_ms=round(avg_lat, 2),
            bytes_on_disk=bytes_on_disk,
            section_type_distribution=section_type_distribution or {},
        )
