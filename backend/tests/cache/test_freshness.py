import time

from backend.cache.freshness import DAY, is_fresh, staleness_reason, ttl_for
from backend.cache.models.cache_entry import CacheEntry


def _entry(section_type: str | None, age_days: float, good_answer) -> CacheEntry:
    return CacheEntry(
        cache_key="k",
        normalized_query="q",
        original_query="Q",
        answer=good_answer,
        grounding_confidence=0.7,
        hallucination_risk=0.05,
        primary_section_type=section_type,
        created_at=time.time() - age_days * DAY,
        last_used_at=time.time(),
    )


def test_ttl_known_section_types() -> None:
    assert ttl_for("admissions") == 7 * DAY
    assert ttl_for("fees") == 30 * DAY
    assert ttl_for("curriculum") == 90 * DAY
    assert ttl_for("events") == 3 * DAY


def test_ttl_unknown_section_falls_back_to_default() -> None:
    assert ttl_for("totally_unknown") == 14 * DAY
    assert ttl_for(None) == 14 * DAY


def test_is_fresh_within_ttl(good_answer) -> None:
    e = _entry("admissions", age_days=2, good_answer=good_answer)
    assert is_fresh(e) is True
    assert staleness_reason(e) is None


def test_is_fresh_past_ttl(good_answer) -> None:
    e = _entry("events", age_days=10, good_answer=good_answer)
    assert is_fresh(e) is False
    assert staleness_reason(e).startswith("stale:")
