import json
import time as _time

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from backend.answering.followup_resolution import resolve_followup_query
from backend.answering.grounded_answering import GroundedAnsweringService
from backend.answering.models.answer import GroundedAnswer, LatencyBreakdown
from backend.api.chat_models import AnswerRequest, CacheHitInfo, ChatRequest, ChatResponse
from backend.api.chat_ui import CHAT_UI_HTML
from backend.api.tts_service import DEFAULT_VOICE, synthesize_mp3
from backend.cache.cache_router import CacheRouter
from backend.cache.models.cache_entry import CacheStats
from backend.cache.semantic_cache import SemanticCache
from backend.config.settings import settings
from backend.context.context_builder import build_grounded_context
from backend.context.validators import ContextBuildRequest, GroundedContext
from backend.conversation.memory import ConversationMemory
from backend.conversation.session_manager import ensure_session_id
from backend.ingestion.models.document import IngestionStats
from backend.ingestion.services.ingestion_service import IngestionService
from backend.llm.factory import get_provider
from backend.llm.prompts.grounded_answering import SYSTEM_PROMPT, build_user_message
from backend.llm.streaming import to_sse_line
from backend.llm.validators import LLMMessage, LLMRequest
from backend.reranking.validators import RerankedSearchResponse
from backend.retrieval.bm25_service import BM25RetrievalService
from backend.retrieval.dense_retrieval import DenseRetrievalService
from backend.retrieval.hybrid_retrieval import HybridRetrievalService
from backend.retrieval.inspector_html import INSPECTOR_HTML
from backend.retrieval.models.search import SearchResponse
from backend.retrieval.reranked_retrieval import RerankedRetrievalService
from backend.utils.logging import configure_logging

configure_logging()

app = FastAPI(title="College AI Assistant Backend", version="0.1.0")


@app.get("/")
async def root():
    return {"status": "ok", "ui": "/chat/ui", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestionStats)
async def ingest(file: UploadFile = File(...)) -> IngestionStats:
    service = IngestionService()
    file.file.seek(0)
    return service.ingest(file.file)


@app.get("/ingestion/report")
async def ingestion_report() -> dict[str, object]:
    report_path = settings.reports_dir / "ingestion_report.json"
    if not report_path.exists():
        return {"message": "No ingestion report has been generated yet."}
    return json.loads(report_path.read_text(encoding="utf-8"))


_bm25_service: BM25RetrievalService | None = None
_dense_service: DenseRetrievalService | None = None
_hybrid_service: HybridRetrievalService | None = None
_reranked_service: RerankedRetrievalService | None = None
_semantic_cache: SemanticCache | None = None
_conversation_memory = ConversationMemory()


def _get_bm25() -> BM25RetrievalService:
    global _bm25_service
    if _bm25_service is None:
        _bm25_service = BM25RetrievalService()
    return _bm25_service


def _get_dense() -> DenseRetrievalService:
    global _dense_service
    if _dense_service is None:
        _dense_service = DenseRetrievalService()
    return _dense_service


def _get_hybrid() -> HybridRetrievalService:
    global _hybrid_service
    if _hybrid_service is None:
        _hybrid_service = HybridRetrievalService(bm25=_get_bm25(), dense=_get_dense())
    return _hybrid_service


def _get_reranked() -> RerankedRetrievalService:
    global _reranked_service
    if _reranked_service is None:
        _reranked_service = RerankedRetrievalService(hybrid=_get_hybrid())
    return _reranked_service


def _get_cache() -> SemanticCache:
    """Reuses the dense retrieval service's EmbeddingModel — no second BGE model load."""
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCache(embedder=_get_dense().model)
    return _semantic_cache


@app.get("/retrieval/search", response_model=SearchResponse)
async def retrieval_search(
    query: str,
    top_k: int = 5,
    include_components: bool = False,
) -> SearchResponse:
    return _get_bm25().search(
        query=query, top_k=top_k, include_components=include_components
    )


@app.get("/retrieval/dense/search", response_model=SearchResponse)
async def retrieval_dense_search(
    query: str,
    top_k: int = 5,
    include_components: bool = False,
) -> SearchResponse:
    return _get_dense().search(
        query=query, top_k=top_k, include_components=include_components
    )


@app.get("/retrieval/hybrid/search", response_model=SearchResponse)
async def retrieval_hybrid_search(
    query: str,
    top_k: int = 5,
    include_components: bool = False,
) -> SearchResponse:
    return _get_hybrid().search(
        query=query, top_k=top_k, include_components=include_components
    )


@app.get("/retrieval/reranked/search", response_model=RerankedSearchResponse)
async def retrieval_reranked_search(
    query: str,
    top_k: int = 5,
    candidate_pool: int = 20,
    include_components: bool = False,
) -> RerankedSearchResponse:
    return _get_reranked().search(
        query=query,
        top_k=top_k,
        candidate_pool=candidate_pool,
        include_components=include_components,
    )


@app.post("/context/build", response_model=GroundedContext)
async def context_build(request: ContextBuildRequest) -> GroundedContext:
    reranked = _get_reranked().search(
        query=request.query,
        top_k=request.top_k,
        candidate_pool=request.candidate_pool,
        include_components=request.include_components,
    )
    return build_grounded_context(
        query=request.query,
        intent=reranked.intent,
        reranked=reranked.results,
        token_budget=request.token_budget,
        min_confidence=request.min_grounding_confidence,
        min_blocks=request.min_blocks,
    )


def _retrieve_and_build_context(request: AnswerRequest):
    """One retrieval+rerank+context pass. Returns (grounded_context, reranked_response) so
    the caller can use both without re-running the heavy cross-encoder."""
    reranked = _get_reranked().search(
        query=request.query,
        top_k=request.top_k,
        candidate_pool=request.candidate_pool,
        include_components=request.include_components,
    )
    grounded_context = build_grounded_context(
        query=request.query,
        intent=reranked.intent,
        reranked=reranked.results,
        token_budget=request.token_budget,
    )
    return grounded_context, reranked


def _build_grounded_context_for(request: AnswerRequest) -> GroundedContext:
    grounded_context, _ = _retrieve_and_build_context(request)
    return grounded_context


def _build_answering_service(request: AnswerRequest) -> GroundedAnsweringService:
    provider = get_provider(request.provider)
    return GroundedAnsweringService(
        provider=provider,
        model=request.model or "",
        run_judge=request.run_judge,
    )


@app.post("/answer", response_model=GroundedAnswer)
async def answer(request: AnswerRequest) -> GroundedAnswer:
    # Cache lookup first (when enabled) — short-circuits the full RAG pipeline on hit.
    if request.use_cache:
        hit = _get_cache().lookup(request.query)
        if hit is not None:
            cached = hit.entry.answer
            return cached.model_copy(update={"query": request.query})

    grounded_context, reranked = _retrieve_and_build_context(request)
    service = _build_answering_service(request)
    result = service.answer(request.query, grounded_context)
    if request.use_cache:
        _get_cache().store_answer(
            query=request.query,
            answer=result,
            intent=reranked.intent if reranked else None,
            primary_section_type=_primary_section_type(reranked),
            primary_page_type=_primary_page_type(reranked),
        )
    return result


def _primary_section_type(reranked) -> str | None:
    if not reranked or not getattr(reranked, "results", None):
        return None
    counts: dict[str, int] = {}
    for r in reranked.results:
        st = getattr(r, "section_type", None)
        if st:
            counts[st] = counts.get(st, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else None


def _primary_page_type(reranked) -> str | None:
    if not reranked or not getattr(reranked, "results", None):
        return None
    counts: dict[str, int] = {}
    for r in reranked.results:
        pt = getattr(r, "page_type", None)
        if pt:
            counts[pt] = counts.get(pt, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else None


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    t_total = _time.perf_counter()
    session_id = ensure_session_id(request.session_id)
    state = _conversation_memory.append_user_turn(session_id, request.query)
    provider = get_provider(request.provider)

    t_rewrite = _time.perf_counter()
    resolved_query, was_rewritten = resolve_followup_query(
        provider=provider,
        query=request.query,
        state=state,
        model=request.model or "",
    )
    rewrite_ms = (_time.perf_counter() - t_rewrite) * 1000 if was_rewritten else None

    answer_request = AnswerRequest(
        query=resolved_query,
        top_k=request.top_k,
        candidate_pool=request.candidate_pool,
        token_budget=request.token_budget,
        include_components=request.include_components,
        run_judge=request.run_judge,
        provider=request.provider,
        model=request.model,
    )

    # ── Cache lookup (after rewrite, before retrieval). On hit we skip retrieval + LLM.
    cache_info = CacheHitInfo()
    cached_hit = _get_cache().lookup(resolved_query) if request.use_cache else None
    if cached_hit is not None:
        cached_answer = cached_hit.entry.answer.model_copy(
            update={
                "query": request.query,
                "rewritten_query": resolved_query if was_rewritten else None,
            }
        )
        cache_info = CacheHitInfo(
            hit=True,
            similarity=cached_hit.similarity,
            primary_section_type=cached_hit.entry.primary_section_type,
            cache_age_seconds=round(_time.time() - cached_hit.entry.created_at, 1),
        )
        cached_answer.latency = LatencyBreakdown(
            rewrite_ms=round(rewrite_ms, 1) if rewrite_ms is not None else None,
            total_ms=round((_time.perf_counter() - t_total) * 1000, 1),
        )
        state = _conversation_memory.append_assistant_turn(
            session_id=session_id,
            content=cached_answer.answer,
            citations=[c.chunk_id for c in cached_answer.citations],
            rewritten_query=resolved_query if was_rewritten else None,
            intent=cached_hit.entry.intent,
            used_chunks=cached_answer.used_chunks,
        )
        return ChatResponse(
            session_id=session_id,
            answer=cached_answer,
            rewritten_query=resolved_query if was_rewritten else None,
            was_rewritten=was_rewritten,
            cache=cache_info,
            conversation_state=state,
        )

    t_retrieval = _time.perf_counter()
    grounded_context, reranked_response = _retrieve_and_build_context(answer_request)
    retrieval_ms = (_time.perf_counter() - t_retrieval) * 1000
    routing_filters = {
        "page_types": list(reranked_response.allowed_page_types),
        "section_types": list(reranked_response.allowed_section_types),
    }

    service = _build_answering_service(answer_request)
    t_llm = _time.perf_counter()
    grounded_answer = service.answer(
        query=resolved_query,
        grounded_context=grounded_context,
        rewritten_query=resolved_query if was_rewritten else None,
    )
    llm_total_ms = (_time.perf_counter() - t_llm) * 1000

    # Store eligible answers on miss.
    if request.use_cache:
        _get_cache().store_answer(
            query=resolved_query,
            answer=grounded_answer,
            intent=reranked_response.intent,
            primary_section_type=_primary_section_type(reranked_response),
            primary_page_type=_primary_page_type(reranked_response),
        )
    # Split LLM total into generate vs judge using the token counts (judge ran iff judge_used).
    if grounded_answer.hallucination.judge_used:
        # Approximate: judge tokens ≈ judge_input+output; split proportional to total.
        judge_tokens = (
            grounded_answer.usage.judge_input_tokens + grounded_answer.usage.judge_output_tokens
        )
        gen_tokens = (
            grounded_answer.usage.input_tokens + grounded_answer.usage.output_tokens
        )
        denom = max(judge_tokens + gen_tokens, 1)
        judge_ms = llm_total_ms * (judge_tokens / denom)
        llm_generate_ms = llm_total_ms - judge_ms
    else:
        judge_ms = None
        llm_generate_ms = llm_total_ms

    grounded_answer.latency = LatencyBreakdown(
        rewrite_ms=round(rewrite_ms, 1) if rewrite_ms is not None else None,
        retrieval_ms=round(retrieval_ms, 1),
        llm_generate_ms=round(llm_generate_ms, 1),
        judge_ms=round(judge_ms, 1) if judge_ms is not None else None,
        total_ms=round((_time.perf_counter() - t_total) * 1000, 1),
    )

    state = _conversation_memory.append_assistant_turn(
        session_id=session_id,
        content=grounded_answer.answer,
        citations=[c.chunk_id for c in grounded_answer.citations],
        rewritten_query=resolved_query if was_rewritten else None,
        intent=reranked_response.intent,
        routing_filters=routing_filters,
        used_chunks=grounded_answer.used_chunks,
    )

    return ChatResponse(
        session_id=session_id,
        answer=grounded_answer,
        rewritten_query=resolved_query if was_rewritten else None,
        was_rewritten=was_rewritten,
        cache=cache_info,
        conversation_state=state,
    )


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Stream answer tokens via Server-Sent Events. The grounded context is built
    synchronously (retrieval is fast); only the LLM generation is streamed."""
    session_id = ensure_session_id(request.session_id)
    state = _conversation_memory.append_user_turn(session_id, request.query)
    provider = get_provider(request.provider)

    resolved_query, was_rewritten = resolve_followup_query(
        provider=provider, query=request.query, state=state, model=request.model or "",
    )
    answer_request = AnswerRequest(
        query=resolved_query,
        top_k=request.top_k,
        candidate_pool=request.candidate_pool,
        token_budget=request.token_budget,
        include_components=request.include_components,
        run_judge=False,
        provider=request.provider,
        model=request.model,
    )
    grounded_context = _build_grounded_context_for(answer_request)
    user_message = build_user_message(resolved_query, grounded_context.prompt)
    llm_request = LLMRequest(
        system_prompt=SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user_message)],
        model=request.model or provider.default_model,
        temperature=0.0,
        max_tokens=500,
    )

    def event_stream():
        # Include the numbered candidate citations so the chat UI can:
        # (a) auto-preview the top source page immediately as streaming starts, and
        # (b) make [N] markers in the streamed answer clickable to switch the preview.
        # The [N] indices in the LLM's output map 1:1 to these context_blocks because the
        # prompt assembler numbers them in the same order.
        opening = {
            "session_id": session_id,
            "rewritten_query": resolved_query if was_rewritten else None,
            "was_rewritten": was_rewritten,
            "intent": grounded_context.intent,
            "grounding_confidence": grounded_context.grounding_confidence,
            "citations": [
                {
                    "index": i + 1,
                    "source_url": block.source_url,
                    "title": block.title,
                    "section_path": list(block.section_path or []),
                }
                for i, block in enumerate(grounded_context.context_blocks)
            ],
        }
        yield b"event: meta\ndata: " + json.dumps(opening).encode() + b"\n\n"
        if not grounded_context.context_blocks:
            yield b"event: abstain\ndata: " + json.dumps(
                {"reason": "no_context_blocks"}
            ).encode() + b"\n\n"
            return
        try:
            for chunk in provider.stream(llm_request):
                yield to_sse_line(chunk)
        except Exception as exc:
            text = str(exc)
            kind = "rate_limit" if "rate limit" in text.lower() or "429" in text else "error"
            err_payload = {"error": text, "kind": kind}
            yield (b"event: " + kind.encode() + b"\ndata: " + json.dumps(err_payload).encode() + b"\n\n")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/conversation/{session_id}")
async def conversation_state(session_id: str):
    if session_id not in _conversation_memory:
        return {"session_id": session_id, "exists": False}
    return _conversation_memory.get(session_id)


@app.delete("/conversation/{session_id}")
async def reset_conversation(session_id: str):
    _conversation_memory.reset(session_id)
    return {"session_id": session_id, "reset": True}


@app.get("/cache/stats", response_model=CacheStats)
async def cache_stats() -> CacheStats:
    return _get_cache().stats()


@app.get("/cache/inspect")
async def cache_inspect(limit: int = 25):
    """Return the most recently used cache entries for debugging."""
    entries = sorted(
        _get_cache().all_entries(), key=lambda e: e.last_used_at, reverse=True
    )[:limit]
    return [
        {
            "cache_key": e.cache_key,
            "normalized_query": e.normalized_query,
            "original_query": e.original_query,
            "primary_section_type": e.primary_section_type,
            "primary_page_type": e.primary_page_type,
            "grounding_confidence": e.grounding_confidence,
            "hallucination_risk": e.hallucination_risk,
            "hit_count": e.hit_count,
            "created_at": e.created_at,
            "last_used_at": e.last_used_at,
            "answer_preview": e.answer.answer[:150],
            "citations": [c.source_url for c in e.answer.citations],
        }
        for e in entries
    ]


@app.delete("/cache/clear")
async def cache_clear():
    cleared = _get_cache().clear()
    return {"cleared": cleared}


@app.get("/chat/ui", response_class=HTMLResponse)
async def chat_ui() -> str:
    return CHAT_UI_HTML


@app.get("/chat/provider")
async def chat_provider() -> dict[str, str]:
    """What provider would `/chat` use right now? Lets the UI display 'gemini' vs 'mock'."""
    provider = get_provider()
    return {"provider": provider.name, "default_model": provider.default_model}


@app.post("/tts")
async def tts(payload: dict) -> StreamingResponse:
    """Stream MP3 audio of `text` using Microsoft Edge's free neural TTS.
    Body: {"text": "...", "voice": "en-IN-NeerjaNeural"} — voice is optional."""
    text = (payload or {}).get("text", "")
    voice = (payload or {}).get("voice") or DEFAULT_VOICE
    return StreamingResponse(synthesize_mp3(text, voice), media_type="audio/mpeg")


@app.get("/retrieval/inspect", response_class=HTMLResponse)
async def retrieval_inspector() -> str:
    return INSPECTOR_HTML
