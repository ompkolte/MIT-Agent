"""CAG-lite vs RAG-only side-by-side benchmark.

Runs each query twice: first call primes the cache (full RAG path), second call should
hit the cache. Compares latency, citation parity, and confidence parity.

Usage:
    python -m backend.scripts.cache_benchmark
"""

from __future__ import annotations

import time
from pathlib import Path
from statistics import mean

import orjson

from backend.api.chat_models import AnswerRequest
from backend.answering.grounded_answering import GroundedAnsweringService
from backend.cache.invalidation import invalidate_all
from backend.cache.semantic_cache import SemanticCache
from backend.context.context_builder import build_grounded_context
from backend.llm.factory import get_provider
from backend.retrieval.reranked_retrieval import RerankedRetrievalService


QUERIES = [
    "What is MCA eligibility?",
    "What is the fee structure for BTech?",
    "Who is the dean of mechanical engineering?",
    "What are the placement statistics?",
    "What is the hostel like?",
    "Tell me about the IEEE student branch.",
    "What is the curriculum for BTech CSE?",
    "How is admission to BTech done?",
    "What is the BTech ENTC curriculum?",
    "Does MITAOE have NAAC accreditation?",
]


def _primary_section(reranked) -> str | None:
    if not reranked.results:
        return None
    counts: dict[str, int] = {}
    for r in reranked.results:
        if r.section_type:
            counts[r.section_type] = counts.get(r.section_type, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else None


def run_one(query: str, retrieval, answering, cache, use_cache: bool) -> dict:
    start = time.perf_counter()
    if use_cache:
        hit = cache.lookup(query)
        if hit is not None:
            return {
                "query": query,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                "path": "cache",
                "similarity": hit.similarity,
                "n_citations": len(hit.entry.answer.citations),
                "grounding_confidence": hit.entry.grounding_confidence,
            }
    rerank = retrieval.search(query, top_k=7, candidate_pool=20)
    ctx = build_grounded_context(query=query, intent=rerank.intent, reranked=rerank.results)
    answer = answering.answer(query=query, grounded_context=ctx)
    if use_cache:
        cache.store_answer(
            query=query, answer=answer,
            intent=rerank.intent, primary_section_type=_primary_section(rerank),
        )
    return {
        "query": query,
        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        "path": "rag",
        "similarity": None,
        "n_citations": len(answer.citations),
        "grounding_confidence": answer.confidence.grounding_confidence,
    }


def main() -> None:
    retrieval = RerankedRetrievalService(candidate_pool=20)
    provider = get_provider()
    answering = GroundedAnsweringService(provider=provider, run_judge=False)
    cache = SemanticCache(embedder=retrieval.hybrid.dense.model)

    # Start from a clean slate so the benchmark is repeatable.
    invalidate_all(cache.store, cache.index)

    print(f"Provider: {provider.name}/{provider.default_model}")
    print(f"Cache start: {cache.stats().total_entries} entries\n")

    # ----- Phase 1: prime (RAG only, no cache reads — fills the cache as a side effect)
    prime_results = [run_one(q, retrieval, answering, cache, use_cache=True) for q in QUERIES]

    # ----- Phase 2: replay (cache should now serve hits)
    replay_results = [run_one(q, retrieval, answering, cache, use_cache=True) for q in QUERIES]

    cache_hits = [r for r in replay_results if r["path"] == "cache"]
    rag_replays = [r for r in replay_results if r["path"] == "rag"]

    avg_prime = round(mean(r["latency_ms"] for r in prime_results), 2)
    avg_replay_hit = round(mean(r["latency_ms"] for r in cache_hits), 2) if cache_hits else 0.0
    speedup_x = round(avg_prime / max(avg_replay_hit, 0.01), 2)

    report = {
        "provider": provider.name,
        "model": provider.default_model,
        "queries": len(QUERIES),
        "phase1_prime_avg_ms": avg_prime,
        "phase2_replay_avg_hit_ms": avg_replay_hit,
        "phase2_hit_rate": round(len(cache_hits) / len(replay_results), 4),
        "phase2_rag_replays": len(rag_replays),
        "speedup_on_hit_x": speedup_x,
        "prime": prime_results,
        "replay": replay_results,
        "cache_stats": cache.stats().model_dump(mode="json"),
    }

    report_path = Path("reports/cache_benchmark.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(orjson.dumps(report, option=orjson.OPT_INDENT_2))

    print(f"Phase 1 (prime, full RAG):  avg {avg_prime} ms")
    print(f"Phase 2 (replay):           {len(cache_hits)}/{len(replay_results)} cache hits")
    print(f"                            avg hit latency {avg_replay_hit} ms")
    print(f"                            speedup ≈ {speedup_x}x on hit")
    print(f"\nWrote {report_path}")


if __name__ == "__main__":
    main()
