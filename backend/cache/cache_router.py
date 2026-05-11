from __future__ import annotations

import time

from backend.answering.grounded_answering import GroundedAnsweringService
from backend.answering.models.answer import GroundedAnswer
from backend.cache.models.cache_entry import CacheHit
from backend.cache.semantic_cache import SemanticCache
from backend.context.validators import GroundedContext


def _section_type_of(reranked_response) -> str | None:
    """Pick the most-represented section_type from the reranked results — used to assign
    a per-content TTL when caching the answer."""
    if not reranked_response or not getattr(reranked_response, "results", None):
        return None
    counts: dict[str, int] = {}
    for r in reranked_response.results:
        st = getattr(r, "section_type", None)
        if not st:
            continue
        counts[st] = counts.get(st, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def _page_type_of(reranked_response) -> str | None:
    if not reranked_response or not getattr(reranked_response, "results", None):
        return None
    counts: dict[str, int] = {}
    for r in reranked_response.results:
        pt = getattr(r, "page_type", None)
        if not pt:
            continue
        counts[pt] = counts.get(pt, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


class CacheRouter:
    """Sits in front of the answering pipeline. On each call:
      1. Look up the query in the semantic cache.
      2. If hit → return cached GroundedAnswer immediately (no retrieval, no LLM).
      3. If miss → call answering_fn() (full RAG), then conditionally store the result.

    The router never bypasses grounding — cached entries had to pass `is_cacheable` when
    stored AND `is_hit_still_valid` on lookup. Misses degrade gracefully to full RAG."""

    def __init__(self, cache: SemanticCache, answering: GroundedAnsweringService) -> None:
        self.cache = cache
        self.answering = answering

    def answer(
        self,
        query: str,
        grounded_context: GroundedContext,
        rewritten_query: str | None = None,
        reranked_response=None,
    ) -> tuple[GroundedAnswer, CacheHit | None, float]:
        """Returns (answer, cache_hit_or_none, total_latency_ms). The optional
        rewritten_query is the post-followup-resolution query that should drive cache
        lookup; if None, falls back to `query`."""
        start = time.perf_counter()
        lookup_query = rewritten_query or query

        hit = self.cache.lookup(lookup_query)
        if hit is not None:
            total_ms = (time.perf_counter() - start) * 1000.0
            cached = hit.entry.answer
            # Stamp the query field with what the caller asked, not the original cached query.
            updated = cached.model_copy(update={"query": query, "rewritten_query": rewritten_query})
            return updated, hit, total_ms

        answer = self.answering.answer(
            query=lookup_query,
            grounded_context=grounded_context,
            rewritten_query=rewritten_query,
        )
        stored, _reason = self.cache.store_answer(
            query=lookup_query,
            answer=answer,
            intent=getattr(reranked_response, "intent", None) if reranked_response else None,
            primary_section_type=_section_type_of(reranked_response),
            primary_page_type=_page_type_of(reranked_response),
        )
        total_ms = (time.perf_counter() - start) * 1000.0
        return answer, None, total_ms
