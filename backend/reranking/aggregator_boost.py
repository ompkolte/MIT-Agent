from __future__ import annotations

import regex as re


# URL patterns that mark a chunk as an "aggregator" / "index" page — pages that exist
# specifically to enumerate all instances of some category (clubs, courses, facilities).
# These chunks are uniquely valuable for "list everything" queries because the
# comprehensive listing exists in one place, and they're easily evicted by token budget
# if not given priority. A small rerank boost lets them survive even when their
# cross-encoder score is mid-pack.
_AGGREGATOR_URL_PATTERNS = [
    r"/student-clubs\.php",
    r"/mitaoe-courses\.php",
    r"/clubs?/?$",
    r"/courses?/?$",
    r"/departments?/?$",
    r"-list\.php",
    r"/all-",
]


# Paragraph density: aggregator pages often have many short paragraphs (one per item).
_PARAGRAPH_MIN_COUNT = 8


def is_aggregator_chunk(url: str, text: str) -> bool:
    """Heuristic: aggregator pages have a known URL pattern OR ≥8 short paragraphs that
    each look like a separate enumerated entity ("AALEKH — Art Club", "MITAOE Aero …")."""
    if url:
        lower_url = url.lower()
        for pattern in _AGGREGATOR_URL_PATTERNS:
            if re.search(pattern, lower_url):
                return True
    if not text:
        return False
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= 30]
    if len(paragraphs) < _PARAGRAPH_MIN_COUNT:
        return False
    # Most paragraphs start with a capitalized phrase (likely entity name)
    capitalized = sum(1 for p in paragraphs if re.match(r"^\s*[A-Z][A-Za-z0-9 &\-'’]{2,40}", p))
    return capitalized >= _PARAGRAPH_MIN_COUNT


# Modest score boost — enough to lift the index page from rank ~#6 to ~#2-3 without
# overwhelming the cross-encoder's actual relevance judgement.
AGGREGATOR_BOOST = 0.10


def boost_score(rerank_calibrated: float, url: str, text: str) -> float:
    """Add an aggregator bonus to a rerank score. Returns the boosted value clamped to
    [0, 1]. Non-aggregator chunks return unchanged."""
    if not is_aggregator_chunk(url, text):
        return rerank_calibrated
    return min(1.0, rerank_calibrated + AGGREGATOR_BOOST)
