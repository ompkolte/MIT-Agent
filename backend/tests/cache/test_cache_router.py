from pathlib import Path

import numpy as np

from backend.answering.grounded_answering import GroundedAnsweringService
from backend.answering.models.answer import GroundedAnswer
from backend.cache.cache_router import CacheRouter
from backend.cache.semantic_cache import SemanticCache
from backend.context.validators import Citation, ContextBlock, GroundedContext
from backend.llm.mock_provider import MockLLMProvider


class _Embedder:
    def embed_query(self, text: str) -> np.ndarray:
        import hashlib

        seed = int(hashlib.md5(text.lower().strip().encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(384).astype(np.float32)
        return v / np.linalg.norm(v)


def _ctx(query: str) -> GroundedContext:
    block = ContextBlock(
        chunk_id="c1",
        document_id="d1",
        text="MCA eligibility requires a relevant bachelor degree.",
        citation=Citation(chunk_id="c1", source_url="https://x", title="MCA Admissions"),
        source_url="https://x",
        title="MCA Admissions",
        page_type="Admissions",
        section_type="eligibility",
        section_path=["Admissions", "Eligibility"],
        rerank_score=0.7,
        answerability_score=0.6,
        final_relevance=0.65,
        token_count=10,
    )
    return GroundedContext(
        query=query,
        intent="eligibility_query",
        context_blocks=[block],
        grounding_confidence=0.65,
        token_budget=2000,
        prompt="Question: ...\n\n[1] eligibility text\n",
    )


def _good_answer_text() -> str:
    return "Eligibility requires a relevant bachelor degree [1]."


def test_router_miss_falls_through_to_rag_and_stores(tmp_path: Path) -> None:
    cache = SemanticCache(embedder=_Embedder(), db_path=tmp_path / "c.db")
    answering = GroundedAnsweringService(
        provider=MockLLMProvider(canned_response=_good_answer_text()),
        run_judge=False,
    )
    router = CacheRouter(cache=cache, answering=answering)

    answer, hit, _ms = router.answer(query="What is MCA eligibility?", grounded_context=_ctx("Q"))
    assert hit is None
    assert "Eligibility" in answer.answer
    assert cache.stats().total_entries == 1


def test_router_hit_returns_cached_without_calling_llm(tmp_path: Path) -> None:
    cache = SemanticCache(embedder=_Embedder(), db_path=tmp_path / "c.db")
    # First provider returns a correct, cacheable answer (primes the cache)
    primer = MockLLMProvider(canned_response=_good_answer_text())
    answering = GroundedAnsweringService(provider=primer, run_judge=False)
    router = CacheRouter(cache=cache, answering=answering)

    answer1, _, _ = router.answer(query="What is MCA eligibility?", grounded_context=_ctx("Q"))
    assert "Eligibility" in answer1.answer

    # Swap provider — second call must hit cache and not invoke this corrupt provider
    answering.provider = MockLLMProvider(canned_response="CORRUPTED NO CITATION")

    answer2, hit, _ = router.answer(query="What is MCA eligibility?", grounded_context=_ctx("Q"))
    assert hit is not None
    assert hit.similarity > 0.99
    assert "Eligibility" in answer2.answer
    assert "CORRUPTED" not in answer2.answer


def test_router_does_not_cache_abstentions(tmp_path: Path) -> None:
    cache = SemanticCache(embedder=_Embedder(), db_path=tmp_path / "c.db")
    answering = GroundedAnsweringService(
        provider=MockLLMProvider(),
        run_judge=False,
    )
    router = CacheRouter(cache=cache, answering=answering)

    empty_ctx = GroundedContext(
        query="oops",
        intent="general_query",
        context_blocks=[],
        grounding_confidence=0.0,
        grounding_warnings=["no_blocks"],
        token_budget=2000,
    )
    answer, hit, _ = router.answer(query="oops", grounded_context=empty_ctx)
    assert hit is None
    assert answer.abstained is True
    assert cache.stats().total_entries == 0


def test_router_uses_rewritten_query_as_lookup_key(tmp_path: Path) -> None:
    """The router must look up using the rewritten (canonicalized) query so 'what about
    fees?' resolves to the cached entry for 'fees for MCA'."""
    cache = SemanticCache(embedder=_Embedder(), db_path=tmp_path / "c.db")
    answering = GroundedAnsweringService(
        provider=MockLLMProvider(canned_response=_good_answer_text()),
        run_judge=False,
    )
    router = CacheRouter(cache=cache, answering=answering)
    # Prime with the rewritten query
    router.answer(
        query="ignored", grounded_context=_ctx("Q"), rewritten_query="What are the fees for MCA?",
    )
    # Now ask with a different surface form but same rewritten query
    _, hit, _ = router.answer(
        query="and fees?", grounded_context=_ctx("Q"), rewritten_query="What are the fees for MCA?",
    )
    assert hit is not None
