from __future__ import annotations

import time

from backend.cache.models.cache_entry import CacheEntry


# TTL per spec, in seconds. Section types from Phase 2 are the closest proxy for
# "content type" (admissions / fees / faculty / curriculum / events / faq).
SECONDS = 1
DAY = 86_400

DEFAULT_TTL_SECONDS = 14 * DAY
TTL_BY_SECTION_TYPE: dict[str, int] = {
    "admissions": 7 * DAY,
    "eligibility": 7 * DAY,
    "fees": 30 * DAY,
    "faculty": 14 * DAY,
    "curriculum": 90 * DAY,
    "syllabus": 90 * DAY,
    "events": 3 * DAY,
    "faq": 30 * DAY,
    "placements": 14 * DAY,
    "research": 30 * DAY,
    "facilities": 30 * DAY,
    "hostel": 30 * DAY,
    "clubs": 14 * DAY,
    "internships": 14 * DAY,
}


def ttl_for(section_type: str | None) -> int:
    """Seconds before the entry is considered stale."""
    if not section_type:
        return DEFAULT_TTL_SECONDS
    return TTL_BY_SECTION_TYPE.get(section_type.lower(), DEFAULT_TTL_SECONDS)


def is_fresh(entry: CacheEntry, now: float | None = None) -> bool:
    now = now if now is not None else time.time()
    return (now - entry.created_at) <= ttl_for(entry.primary_section_type)


def staleness_reason(entry: CacheEntry, now: float | None = None) -> str | None:
    if is_fresh(entry, now):
        return None
    age_days = (((now or time.time()) - entry.created_at) / DAY)
    ttl_days = ttl_for(entry.primary_section_type) / DAY
    return f"stale:{age_days:.1f}d>{ttl_days:.0f}d_for_{entry.primary_section_type or 'default'}"
