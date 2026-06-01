---
title: MITAOE Assistant
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# MITAOE Assistant

A grounded, retrieval-augmented question-answering system for **MIT Academy of Engineering (MITAOE)**. Built as an explainable RAG stack — every answer is grounded in a specific chunk of the institutional corpus, cited inline, and validated before being shown to the user.

The system answers questions about admissions, eligibility, fees, faculty, placements, curriculum, hostels, clubs, events, and more. Includes a split-pane chat UI with live source-page preview and a fully optional voice mode (speech-to-text input + neural text-to-speech output).

---

## Table of contents

1. [What it does](#what-it-does)
2. [Tech stack](#tech-stack)
3. [Architecture at a glance](#architecture-at-a-glance)
4. [What's been built (phase by phase)](#whats-been-built-phase-by-phase)
5. [Quick start](#quick-start)
6. [Offline pipeline — from CSV to vectors](#offline-pipeline--from-csv-to-vectors)
7. [Running the server](#running-the-server)
8. [Using the UI](#using-the-ui)
9. [API reference](#api-reference)
10. [Tests](#tests)
11. [Project layout](#project-layout)
12. [Configuration / environment variables](#configuration--environment-variables)
13. [Design principles](#design-principles)

---

## What it does

- Ingests a scraped CSV of the MITAOE website (~934 pages, ~11 MB) and turns it into a clean, deduplicated, classified corpus.
- Builds a hybrid retrieval index: **BM25 (lexical) + Dense (BAAI/bge-small-en-v1.5) → reciprocal-rank fusion → cross-encoder rerank (BAAI/bge-reranker-base)**.
- Assembles a token-budgeted, citation-numbered context block and asks an LLM (Groq / Gemini / Claude / OpenAI / Mock) to answer **only** from that context.
- Validates the answer: abstention guard, grounding confidence, optional LLM-as-judge hallucination check.
- Caches grounded answers in a semantic SQLite cache keyed by query embedding (CAG-lite) for instant repeat answers.
- Streams the answer over Server-Sent Events while a split-pane UI auto-loads the first cited source page in an iframe on the right.
- Optional voice mode: browser-native speech recognition for input, Microsoft Edge's free neural TTS for spoken replies.

---

## Tech stack

| Layer | Tech |
|---|---|
| Language / runtime | Python 3.11+ |
| Web framework | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| Ingestion | pandas, BeautifulSoup4, trafilatura, regex, rapidfuzz |
| NLP | spaCy, tiktoken |
| Embeddings | sentence-transformers (BAAI/bge-small-en-v1.5, 384-dim) |
| Vector store | Qdrant (local, file-based) |
| Lexical retrieval | rank-bm25 (BM25Okapi) |
| Reranker | BAAI/bge-reranker-base (cross-encoder) |
| LLM providers | Groq (default), Gemini, Anthropic, OpenAI, Mock |
| Semantic cache | SQLite + in-memory numpy embedding index |
| Streaming | SSE (`text/event-stream`) |
| Voice — STT | Web Speech API (browser-native) |
| Voice — TTS | `edge-tts` (Microsoft Edge neural voices, free, no API key) |
| Testing | pytest (340 tests) |
| Container | Dockerfile + docker-compose |

---

## Architecture at a glance

```
                    ┌──────────────────  OFFLINE  ──────────────────┐
   scraped CSV ──▶  ingestion (clean · dedup · classify)
                         │
                         ▼
                    semantic chunker  ──▶  chunks.jsonl
                         │
                         ▼
                    normalization (page type · section type · quality · components · hierarchy)
                         │
                         ▼
                    embedding pipeline (bge-small, skips reusable components)
                         │
                         ▼
                    Qdrant ingest + BM25 corpus on disk
                    └────────────────────────────────────────────────┘

                    ┌──────────────────  ONLINE per query  ─────────┐
   user query  ──▶  followup rewrite (LLM, only if marker)
                         │
                         ▼
                    intent router + query expansion
                         │
                ┌────────┴────────┐
                ▼                 ▼
              BM25 search       Dense search (Qdrant + payload filter)
                │                 │
                └──────┬──────────┘
                       ▼
                 reciprocal rank fusion
                       │
                       ▼
                 cross-encoder rerank → calibrate → answerability blend
                       │
                       ▼
                 dedup + diversity caps
                       │
                       ▼
                 context build (token-budget · citations · grounding)
                       │
                       ▼
                 abstention guard ──▶ LLM answer (stream or sync)
                       │
                       ▼
                 hallucination judge (optional) ──▶ grounded answer
                       │
                       ▼
                 semantic cache write + session memory append
                    └────────────────────────────────────────────────┘
```

A full Mermaid version with every module reference lives in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## What's been built (phase by phase)

The system was built incrementally; each phase is independently testable and reviewable.

### Phase 1 — Ingestion (`backend/ingestion/`)
- CSV loader and row validator.
- HTML extractors (trafilatura primary, BeautifulSoup fallback).
- Cleaners (whitespace, boilerplate strip).
- Deduplication by normalized URL + content hash.
- Page-type classifiers (admissions, programs, faculty, events, notices, …).
- Exports to `datasets/processed_documents.json` and NDJSON.

### Phase 2 — Normalization + routing (`backend/normalization/`, `backend/retrieval/`)
- `page_classifier`, `semantic_section_typer`, `quality_flags`, `canonicalizer`, `retrieval_priority`.
- `intent_router` — maps a query to allowed page-types (admissions / faculty / event / club / general / …).
- `query_expansion` — synonym map (dean↔head, fees↔tuition, entc→electronics and telecommunication, nac→naac, etc.).
- `metadata_filters`, `weighted_ranker`, `bm25_service`.
- Output: routed, weighted BM25 retrieval over `datasets/normalized_chunks.jsonl`.

### Phase 3 — Semantic cleanliness (`backend/normalization/`)
- `boilerplate_registry`, `component_detector`, `widget_suppressor` (with `PRESERVED_CONTENT_PATTERNS` so fee tables / eligibility blocks aren't falsely flagged).
- `hierarchy_extractor`, `heading_classifier`, `section_normalizer`, `semantic_section_splitter`, `contamination_detector`.
- Eliminates 547 reusable components and 38 contaminated chunks from the embedded set.

### Phase 4 — Hybrid retrieval (`backend/embeddings/`, `backend/vectorstore/`, `backend/retrieval/`)
- `embedding_model` (bge-small), `embedding_cache`, `batch_embedder`, `eligibility`.
- Qdrant client + payload mapper + collection manager + ingest + search.
- `dense_retrieval`, `fusion` (RRF, k=60), `hybrid_retrieval`.
- Result: 1308 vectors @ 384-dim with metadata payload.

### Phase 5 — Reranking + context (`backend/reranking/`, `backend/context/`)
- `reranker_model` (cross-encoder), `rerank_service`.
- `score_calibrator` (sigmoid + final blend `0.8·rerank + 0.2·answerability`).
- `answerability` — stats markers, fee-table boost.
- `aggregator_boost` — `+0.10` boost for index/listing URLs (e.g. `/student-clubs.php`) so comprehensive listing chunks survive top-K.
- `duplicate_suppressor` (rapidfuzz, threshold 85).
- `semantic_diversity` — caps per section_type / document; exempts dominant generic types (`overview`/`general`).
- `context_builder`, `citation_builder`, `token_budget` (tiktoken), `grounding`, `prompt_assembler`, `semantic_grouping`, `context_deduplicator`.

### Phase 6 — LLM answering + chat (`backend/llm/`, `backend/answering/`, `backend/conversation/`, `backend/api/`)
- Multi-provider abstraction: `groq_provider`, `gemini_provider`, `claude_provider`, `openai_provider`, `mock_provider`. Provider chosen automatically based on which `*_API_KEY` is set; can be overridden with `LLM_PROVIDER`.
- `answer_generator`, `grounded_answering`, `abstention`, `hallucination_guard` (LLM-as-judge), `confidence`, `citation_formatter`, `answer_validator`, `followup_resolution`.
- `conversation/memory`, `session_manager`, `retrieval_state` (entity tracking), `query_rewriter` (LLM rewrite + length sanity check), `context_window`.
- FastAPI endpoints: `/chat`, `/chat/stream` (SSE), `/conversation/{id}`, `/answer`, `/context/build`, `/retrieval/*`.

### Phase 6.5 — Semantic cache (CAG-lite) (`backend/cache/`)
- `cache_store` (SQLite at `datasets/semantic_cache.db`), `embedding_index` (numpy, in-memory).
- `cache_validator` — eligibility gate (grounding ≥ 0.5, hallucination ≤ 0.3, ≥ 1 citation, not abstained).
- `freshness` — per-section-type TTL.
- `invalidation` — version-keyed eviction.
- `cache_router` — wraps `GroundedAnsweringService`; lookup → hit returns cached; miss falls through to RAG and persists the answer.
- Similarity threshold `0.88` so paraphrases share entries.

### UI extension — split-pane + voice mode (`backend/api/chat_ui.py`, `backend/api/tts_service.py`)
- Two-column grid layout: chat on the left, live source-page iframe preview on the right.
- Auto-load behavior: the preview pane loads the URL of the **first `[N]` cited in the answer text** (not the top-reranked chunk), so the page on the right matches what the LLM actually grounded on. Falls back to top citation if the answer has no markers.
- Click any `[N]` inline pill or citation card to switch the preview.
- Greeting bubble ("Hi! How can I help you with MITAOE today?") on first load and reset.
- Claude-style thinking animation — pulsing dots with a verb that cycles `Thinking → Searching MITAOE → Reading sources → Drafting answer` until the first streamed token arrives.
- **Voice mode** (toggle in toolbar):
  - **STT**: browser-native `SpeechRecognition` — click mic, speak, transcript auto-fills and sends.
  - **TTS**: `edge-tts` (Microsoft Edge neural voices) via `POST /tts`; falls back to browser `speechSynthesis` if the request fails.
  - Voice picker with 7 neural voices (default: Neerja, Indian English female).

---

## Quick start

### Prerequisites
- Python 3.11+
- ~2 GB free disk for models + Qdrant store
- Optional: a Groq API key (recommended — free tier, 14,400 requests/day on `llama-3.1-8b-instant`). Gemini / Anthropic / OpenAI also work.

### Install

```bash
git clone <repo-url> MIT-Agent
cd MIT-Agent

python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

This installs FastAPI, sentence-transformers, Qdrant client, BM25, rapidfuzz, tiktoken, edge-tts, and the provider SDKs.

### Set an API key (optional but recommended)

Create a `.env` file in the project root:

```bash
# pick one (Groq is recommended for the free tier)
GROQ_API_KEY=gsk_...
# GOOGLE_API_KEY=AIza...
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
```

If no key is set, the system falls back to the `MockLLMProvider` (still works end-to-end, but answers are canned).

### Run

The repo ships with prebuilt `datasets/` (normalized chunks + embedded vectors + Qdrant store), so you can run the server directly:

```bash
uvicorn backend.api.main:app --reload --port 8000
```

Open **http://localhost:8000/chat/ui** in Chrome or Edge. Ask a question.

---

## Offline pipeline — from CSV to vectors

If you have a fresh CSV scrape (or want to rebuild the index from scratch), run these scripts in order from the project root:

```bash
# 1. Ingest the scraped CSV → processed_documents.json
#    (the API also exposes POST /ingest if you prefer HTTP)
python -c "
from pathlib import Path
from backend.ingestion.services.ingestion_service import IngestionService
svc = IngestionService()
stats = svc.ingest_csv(Path('dataset_website-content-crawler_2026-05-02_22-33-43-599.csv'))
print(stats.model_dump_json(indent=2))
"

# 2. Semantic chunking → datasets/chunks.jsonl
python backend/scripts/chunk_documents.py

# 3. Normalization (Phase 2+3) is integrated into the chunker output.
#    Produces datasets/normalized_chunks.jsonl.

# 4. Embed chunks (skips reusable components + contaminated) → datasets/embedded_chunks.jsonl
python -m backend.embeddings.embed_chunks

# 5. Ingest into Qdrant local store → datasets/qdrant_storage/
python backend/scripts/qdrant_ingest.py
```

Reports for each stage land in `reports/` (`ingestion_report.json`, `chunking_report.json`, `corpus_normalization_report.json`, `embedding_manifest.json`, etc.).

**Benchmarks** are also run as scripts:

```bash
python backend/scripts/bm25_benchmark.py
python backend/scripts/hybrid_benchmark.py
python backend/scripts/reranking_benchmark.py
python backend/scripts/answer_quality_eval.py
python backend/scripts/cache_benchmark.py
python backend/scripts/verify_50_queries.py
```

---

## Running the server

### Local (recommended for development)

```bash
uvicorn backend.api.main:app --reload --port 8000
```

- Chat UI: `http://localhost:8000/chat/ui`
- Retrieval inspector: `http://localhost:8000/retrieval/inspect`
- OpenAPI docs: `http://localhost:8000/docs`

### Docker

```bash
docker-compose up --build
```

The compose file mounts `./datasets` into the container so Qdrant state persists across rebuilds.

---

## Using the UI

Open `http://localhost:8000/chat/ui`.

**Layout** — two columns: chat on the left, source-page iframe preview on the right.

**Toolbar**:
- `stream tokens` — on by default, uses `/chat/stream` (SSE).
- `run hallucination judge` — off by default (saves one extra LLM call per answer); when on, the judge validates each answer's grounding.
- `🎤 voice mode` — see below.
- `reset chat` — clears the session and re-shows the greeting.

**Asking a question** (text mode):
1. Type and press Enter (or click Send).
2. The thinking animation (`Thinking → Searching MITAOE → …`) plays until the first token streams.
3. The answer streams in with inline `[1] [2] [3]` citation pills.
4. The right pane auto-loads the source page for the **first cited number** in the answer.
5. Click any `[N]` pill or citation card to switch the preview to that source.

**Voice mode**:
1. Tick `🎤 voice mode` in the toolbar — the mic button and voice picker appear.
2. Click the mic, speak your question. The transcript fills the input and auto-sends.
3. When the answer is ready, it's read aloud using the selected Microsoft Edge neural voice.
4. Starting a new turn or clicking the mic stops any in-progress speech.
5. Browser autoplay rules may silently block the very first reply before any click — the text still shows; subsequent replies work normally.

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/ingest` | Ingest a scraped CSV upload. |
| `GET`  | `/ingestion/report` | Stats from the last ingestion run. |
| `GET`  | `/retrieval/search` | BM25-only search. |
| `GET`  | `/retrieval/dense/search` | Dense (Qdrant) search. |
| `GET`  | `/retrieval/hybrid/search` | RRF-fused BM25 + dense. |
| `GET`  | `/retrieval/reranked/search` | Hybrid + cross-encoder rerank. |
| `POST` | `/context/build` | Build a `GroundedContext` for a query (debugging). |
| `POST` | `/answer` | Stateless grounded answer. |
| `POST` | `/chat` | Stateful chat (session memory + followup rewrite). |
| `POST` | `/chat/stream` | Same as `/chat`, SSE streaming. |
| `GET`  | `/conversation/{session_id}` | Inspect session state. |
| `DELETE` | `/conversation/{session_id}` | Clear a session. |
| `GET`  | `/cache/stats` | Semantic-cache size, hit rate, section distribution. |
| `GET`  | `/cache/inspect` | List cached entries. |
| `DELETE` | `/cache/clear` | Wipe the semantic cache. |
| `GET`  | `/chat/ui` | Chat HTML page. |
| `GET`  | `/chat/provider` | Which provider/model is active right now. |
| `POST` | `/tts` | Stream MP3 audio for `{text, voice?}` via Microsoft Edge neural TTS. |
| `GET`  | `/retrieval/inspect` | Retrieval debugger HTML page. |

`POST /chat` body shape:

```json
{
  "query": "what is the fee structure for BTech?",
  "session_id": null,
  "top_k": 10,
  "candidate_pool": 20,
  "token_budget": 4500,
  "run_judge": false,
  "use_cache": true
}
```

---

## Tests

340 tests across the full stack:

```bash
python -m pytest backend/tests/ -q
```

Coverage by module: ingestion, normalization, embeddings, vectorstore, retrieval (BM25 / dense / hybrid / reranked), reranking, context, answering, LLM providers, conversation, semantic cache.

---

## Project layout

```
MIT-Agent/
├── ARCHITECTURE.md                # full Mermaid architecture + per-module map
├── Project_context.md             # project mission and constraints
├── rules_for_coding.md            # internal coding rules
├── pyproject.toml
├── Dockerfile · docker-compose.yml
├── dataset_website-content-crawler_*.csv   # raw scrape input
├── datasets/                       # built artifacts (chunks, embeddings, Qdrant store, cache db)
├── reports/                        # per-phase JSON reports
└── backend/
    ├── api/                # FastAPI app · chat UI · TTS service
    ├── ingestion/          # Phase 1 — CSV → processed docs
    ├── chunking/           # semantic chunker
    ├── normalization/      # Phase 2+3 — section types, components, hierarchy
    ├── embeddings/         # bge-small wrapper + cache + batch
    ├── vectorstore/        # Qdrant client + payload mapper + filters
    ├── retrieval/          # BM25 · dense · hybrid · reranked · intent router · query expansion
    ├── reranking/          # cross-encoder · calibration · diversity · aggregator boost
    ├── context/            # token-budgeted context build + grounding
    ├── llm/                # provider abstraction (Groq · Gemini · Claude · OpenAI · Mock)
    ├── answering/          # grounded answering · abstention · hallucination guard · confidence
    ├── conversation/       # memory · session · followup rewrite · entity tracking
    ├── cache/              # semantic cache (CAG-lite) — SQLite + numpy index
    ├── evaluation/         # quality / grounding / hallucination eval helpers + QA sets
    ├── scripts/            # offline pipeline + benchmark scripts
    ├── config/             # settings
    ├── utils/              # logging
    └── tests/              # 340 pytest cases
```

---

## Configuration / environment variables

| Variable | Purpose | Default |
|---|---|---|
| `LLM_PROVIDER` | Force a provider (`groq` / `gemini` / `anthropic` / `openai` / `mock`). If unset, the first provider whose API key is set wins. | auto |
| `GROQ_API_KEY` | Groq key (recommended). | — |
| `GOOGLE_API_KEY` | Gemini key. | — |
| `ANTHROPIC_API_KEY` | Claude key. | — |
| `OPENAI_API_KEY` | OpenAI key. | — |

Default model per provider lives in [backend/llm/model_registry.py](backend/llm/model_registry.py):

- Groq → `llama-3.1-8b-instant`
- Gemini → `gemini-2.5-flash`
- Anthropic → `claude-sonnet-4-6`
- OpenAI → `gpt-4.1-mini`

---

## Design principles

1. **Grounded or abstain** — if the retrieval grounding confidence falls below threshold, the system abstains rather than hallucinating.
2. **Every claim is citable** — the LLM is prompted to cite `[N]` for every fact; answers without citations are flagged.
3. **Deterministic retrieval before fancy generation** — chunk quality, metadata routing, and rerank stability matter more than the LLM model.
4. **Explainability over magic** — the retrieval inspector, cache inspector, and confidence pills make the pipeline's decisions visible.
5. **Provider-agnostic LLM layer** — switching from Groq to Gemini is one env var; the rest of the system doesn't care.
6. **Offline-first artifacts** — the CSV → chunks → vectors pipeline is reproducible from scripts; the online server only reads.
