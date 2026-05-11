from backend.cache.cache_metrics import CacheMetrics


def test_hit_rate_zero_when_no_lookups() -> None:
    m = CacheMetrics()
    assert m.hit_rate == 0.0


def test_hit_rate() -> None:
    m = CacheMetrics()
    m.record_hit(0.95)
    m.record_hit(0.97)
    m.record_miss()
    assert m.hit_rate == round(2 / 3, 4) or abs(m.hit_rate - 2 / 3) < 1e-9


def test_snapshot_includes_aggregates() -> None:
    m = CacheMetrics()
    m.record_hit(0.95, latency_saved_ms=120.0)
    m.record_hit(0.97, latency_saved_ms=200.0)
    s = m.snapshot(total_entries=5, section_type_distribution={"fees": 5})
    assert s.total_entries == 5
    assert s.total_hits == 2
    assert s.avg_similarity_at_hit == 0.96
    assert s.avg_latency_saved_ms == 160.0
    assert s.section_type_distribution == {"fees": 5}


def test_reset() -> None:
    m = CacheMetrics()
    m.record_hit(0.95)
    m.record_miss()
    m.reset()
    assert m.hits == 0
    assert m.misses == 0
