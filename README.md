# Audio Briefing Engine

Generate short (~5 min) audio news briefings from Hacker News. Enter optional interest keywords, and an LLM agent fetches relevant articles, summarizes them for audio, and produces per-article MP3s you can play individually.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Gradio UI (mounted on FastAPI at "/")                      │
│  [interests input] [Generate Briefing]                      │
│  Per-article cards with ▶ play, transcript, HN link         │
└──────────────────────────┬──────────────────────────────────┘
                           │
              POST /api/briefings → 202 {job_id}
              GET  /api/briefings/{id} → poll status
              GET  /api/briefings/{id}/audio/{index} → MP3
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  FastAPI Backend                                            │
│                                                             │
│  api.py ──▶ jobs.py ──▶ agent.py (gpt-5-mini)              │
│                              │                              │
│                    ┌─────────┼──────────┐                   │
│                    ▼                    ▼                    │
│             search_hn()          read_url()                 │
│             (Algolia API)        (Jina Reader)              │
│                    tools.py                                 │
│                                                             │
│              Agent returns BriefingScript                    │
│                         │                                   │
│                         ▼                                   │
│                  tts.py (OpenAI TTS)                         │
│                  Parallel per-article MP3                    │
└─────────────────────────────────────────────────────────────┘
```

### Module Breakdown

| Module | Responsibility |
|--------|---------------|
| `app/config.py` | Pydantic-settings singleton, env validation |
| `app/models.py` | 13 Pydantic models (articles, jobs, errors) |
| `app/tools.py` | `search_hn()` + `read_url()` — async HTTP to Algolia/Jina |
| `app/agent.py` | Multi-turn LLM agent loop with tool dispatch |
| `app/tts.py` | Parallel TTS pipeline, per-article MP3 generation |
| `app/jobs.py` | In-memory job store, orchestrator, error aggregation |
| `app/api.py` | REST endpoints (create, poll, stream audio) |
| `app/ui.py` | Gradio Blocks UI with async polling handler |
| `app/main.py` | FastAPI app assembly, Gradio mount, lifespan hooks |

### Error Handling

Six-layer error propagation — errors are data, never unhandled exceptions:

1. **External APIs** (Algolia, Jina, OpenAI) — HTTP errors caught in tools
2. **Tools** — return error strings to the agent + log `BriefingError`
3. **Agent loop** — turn limits, token budgets, timeouts, parse failures
4. **TTS pipeline** — per-article retry, partial failure tolerance (>50% must succeed)
5. **Job manager** — aggregates all errors, always produces structured result
6. **API/UI** — surfaces status + actionable messages to the user

## How the Search Strategy Works

The agent follows a **search → evaluate → read → write** process:

1. **Search**: The agent calls `search_hn()` with 2-3 related search terms derived from the user's interests. No interests = today's top stories sorted by points. Each search hits the Algolia HN API, capped at 15 results per query.

2. **Evaluate**: The agent mentally ranks articles by diversity, substance, and newsworthiness. It skips job postings, low-engagement Show HNs, and duplicate topics.

3. **Read**: The agent calls `read_url()` on selected articles (typically 5-10) to fetch full content via Jina Reader. Multiple reads execute in parallel within a single agent turn. Content is truncated to 2,000 chars to manage the token budget. If a read fails (paywall, timeout), the agent adapts and writes a brief mention from the title only.

4. **Write**: The agent produces a `BriefingScript` JSON with self-contained 60-80 word summaries per article, written for the ear — short sentences, no markdown, no jargon.

### Guardrails

- **15-turn limit** — agent is forced to finalize if it hasn't after 15 turns
- **100K token budget** — `tool_choice="none"` injected to force output generation
- **120s wall-clock timeout** — `asyncio.wait_for` wraps the entire loop
- **URL fragment deduplication** — `urldefrag()` strips `#fragment` before cache lookup to prevent redundant reads

## Caching Strategy

Three cache layers reduce API calls and avoid redundant work:

| Cache | Key | TTL | Store | Purpose |
|-------|-----|-----|-------|---------|
| Algolia search results | `query + sort + limit` | 5 min | In-memory `TTLCache` | Avoid re-hitting Algolia for the same query within a session |
| Jina article content | URL (fragment-stripped) | 1 hour | In-memory `TTLCache` | Same article read by multiple jobs reuses cached content |
| Per-article audio | `SHA256(hn_id + summary_text)` | 24 hours | Filesystem (`/tmp/briefings/`) | Identical summaries skip TTS entirely |

- **URL normalization**: `urldefrag()` strips `#fragment` before cache lookup, so `example.com/page` and `example.com/page#section` share a single cache entry and a single Jina fetch.
- **Content-addressed audio**: Audio is keyed by a hash of the article ID and summary text, not the job ID. If two jobs produce the same summary for the same article, the second job reuses the existing MP3.
- **Startup cleanup**: `cleanup_old_audio()` and `cleanup_old_jobs()` run at app startup to evict expired entries based on the 24-hour TTL.

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd audio-briefing-engine
uv sync

# Configure
cp .env.example .env
# Edit .env — set OPENAI_API_KEY (required)

# Run
uv run python -m app.main
# Open http://localhost:8000
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | OpenAI API key |
| `JINA_API_KEY` | (optional) | Jina Reader key for higher rate limits |
| `OPENAI_MODEL` | `gpt-5-mini` | Agent LLM model |
| `OPENAI_TTS_MODEL` | `tts-1` | TTS model |
| `OPENAI_TTS_VOICE` | `onyx` | TTS voice (news anchor tone) |
| `AGENT_MAX_TURNS` | `15` | Max agent loop iterations |
| `AGENT_TIMEOUT_SECONDS` | `120` | Wall-clock timeout for agent |
| `MAX_ARTICLE_CONTENT_LENGTH` | `2000` | Chars per article (token budget control) |
| `MAX_SEARCH_RESULTS` | `15` | Results per Algolia query |

### Docker

```bash
docker compose up --build
```

## Testing

```bash
# Unit tests (mocked, free, fast)
uv run pytest tests/ -m "not integration and not eval" -v

# Integration tests (hits Algolia/Jina APIs)
uv run pytest tests/ -m integration -v

# Eval suite (calls OpenAI, ~$0.15 per run)
uv run pytest tests/evals/ -m eval -v -s --timeout=300
```

## Evaluation Suite

The eval suite tests two surfaces using a session-scoped fixture that runs the real agent once with mocked tools (pre-scraped articles), then shares the results across all 13 tests.

### Surface 1: Summary Quality (LLM-as-judge via DeepEval)

Uses `gpt-4o-mini` as a judge model to evaluate each article summary:

| Metric | Threshold | What It Checks |
|--------|-----------|----------------|
| Faithfulness | >= 0.7 | Every claim in the summary is supported by the source article |
| Coverage | >= 0.5 | Summary captures the main subject, why it matters, and key data points |
| Hallucination | <= 0.3 | Summary doesn't contain fabricated facts (0 = good, 1 = all hallucinated) |
| Conciseness | 50-90 words | Right length for ~30s audio, no markdown or URLs |
| Listenability | >= 0.3 | Written for the ear — short sentences, natural flow, no visual formatting |

### Surface 2: Operational Efficiency (deterministic)

No LLM calls — pure assertions against the agent trace:

| Metric | Target | What It Checks |
|--------|--------|----------------|
| Search calls | 1-5 | Agent doesn't over-search |
| Read calls | >= 3 | Agent reads enough articles for substance |
| No duplicate reads | 0 duplicates | Same URL not read twice |
| Turn count | <= 10 | Agent finishes efficiently |
| Articles produced | >= 3 | Enough content for a briefing |
| Token budget | <= 80K | Stays within cost limits |
| Token growth curve | Report | Per-turn cumulative tokens to identify bottlenecks |
| Latency report | Report | Per-turn and per-tool-call timing breakdown |

### Sample Eval Output

```
Turn | Prompt | Completion | Cumulative | Tool Calls
   1 |    899 |         96 |        995 | 1 call(s)   ← first search
   2 |  1,207 |         97 |      2,299 | 1 call(s)   ← second search
   3 |  1,516 |         30 |      3,845 | 1 call(s)   ← third search
   4 |  1,828 |        192 |      5,865 | 5 call(s)   ← reads all articles
   5 |  2,538 |      4,488 |     12,891 | (finalize)  ← writes summaries
```

## Future Scope: Local Document Ingestion

The architecture is designed for a `search_docs` tool to slot in alongside `search_hn` and `read_url`:

```
v1 (current):              v2 (planned):
  search_hn                  search_hn
  read_url                   read_url
                             search_docs ← NEW (vector search over user's documents)
```

The agent decides which tool to use based on the query — "brief me on today's meetings and top AI news" triggers both `search_docs` and `search_hn` in the same session.

**Planned components:**
- Embedding pipeline using OpenAI `text-embedding-3-small`
- Vector store (Chroma or pgvector) with two-table schema (documents + chunks)
- `POST /api/ingest` endpoint for file uploads (PDF, DOCX, markdown)
- Hybrid scoring: semantic similarity + recency, weighted per source type (meetings favor recency, reference docs favor semantic match)
- UI extension with file upload area and source toggles (HN / My Documents)

See `docs/plan.md` for the full design and `docs/implementation.md` for PR history.
