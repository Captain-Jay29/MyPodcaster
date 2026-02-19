# Audio Briefing Engine

A personal audio briefing system that ingests documents (emails, calendar docs, shared files) and fetches external sources (Hacker News), letting users ask natural language questions and receive spoken audio summaries.

---

## Example Interaction

> **User:** What meetings do I have today?
> **Audio:** You have a meeting with the CEO of ABC Corp at 2 PM. The agenda covers the Q3 rollout of Project XYZ...

> **User:** How can I impress him with Project XYZ? What's Hacker News saying about that space?
> **Audio:** Project XYZ focuses on edge AI deployment — here are three talking points... Meanwhile, HN has been buzzing about edge inference optimization...

---

## Architecture

```
FRONTEND (chat UI)
│  Text input → Audio player responses → Document upload
│
▼
BACKEND (FastAPI)
│
├── Conversation Manager (chat history for follow-ups)
│
├── LLM Agent (tool-use orchestrator)
│   Reasons about the query, calls tools, synthesizes a script
│
├── Tools
│   ├── search_internal_docs(query, filters)
│   ├── fetch_hackernews(topic)
│   ├── get_calendar(date)
│   └── generate_audio(script)
│
├── Document Store (embeddings + metadata in SQLite/Chroma)
│
└── TTS Engine (script → audio)
```

---

## Two Content Paths

**Internal (user's world):** Emails, calendar docs, project briefs, shared files. Uploaded or scanned, embedded, and stored for semantic retrieval.

**External (the world's signal):** Hacker News articles fetched on-demand when the agent determines the query needs live external data.

Both paths converge at the LLM agent, which synthesizes results into a single coherent audio script.

---

## Retrieval: Embeddings + Metadata

**Embeddings** handle semantic matching — a query about "AI regulation" surfaces a doc about "EU foundation model policy" even without keyword overlap.

**Structured metadata** (`source_type`, `date`, `people`, `urgency`) handles concrete filters — "what are my meetings today?" filters by `source_type=calendar, date=today` before any semantic search.

At query time: apply metadata filters → semantic search over remaining docs → top-K results to the agent.

Storage is lightweight at this scale: SQLite for metadata/text, Chroma or in-memory numpy for vectors.

---

## LLM Agent as Orchestrator

Simple retrieval can't handle multi-step queries like the example above. That query requires resolving "him" from conversation history, pulling project docs, extracting a topic, fetching HN, and synthesizing. The agent handles this reasoning loop — embeddings and APIs are just its tools.

The agent receives full conversation history per session, enabling follow-up resolution.

---

## Accuracy Controls

- **Grounded generation**: agent prompt constrains output to retrieved content only
- **Self-check pass**: second LLM call reviews the script against source docs, flags unsupported claims
- **No lossy pre-summarization**: raw text stored at ingestion, summaries generated at query time from full content

---

## Audio Generation

OpenAI TTS API, outputting MP3. Listenability is handled in the script itself — short sentences, transitions between topics, 60–180 seconds per topic. Audio is cached for repeated queries on the same content.

---

## Tech Stack

| Layer          | Technology                       |
| -------------- | -------------------------------- |
| Frontend       | React or plain HTML/JS           |
| Backend        | FastAPI                          |
| LLM            | OpenAI GPT-4o (tool-use)        |
| Embeddings     | OpenAI `text-embedding-3-small`  |
| Vector Store   | Chroma or numpy                  |
| Metadata Store | SQLite                           |
| TTS            | OpenAI TTS API                   |
| External Data  | Hacker News API                  |

---

## API Endpoints

```
POST /api/ingest       — Upload and process a document
POST /api/query        — Ask a question, get an audio briefing
GET  /api/documents    — List ingested documents
GET  /api/audio/{id}   — Serve generated audio
DELETE /api/documents/{id} — Remove a document
```

---

## Project Structure

```
audio-briefing-engine/
├── backend/
│   ├── main.py                  # FastAPI app + endpoints
│   ├── agent.py                 # LLM agent with tool-use
│   ├── tools/
│   │   ├── internal_search.py   # Embedding search + filters
│   │   ├── hackernews.py        # HN API fetch + ranking
│   │   ├── calendar.py          # Calendar event retrieval
│   │   └── tts.py               # Text-to-speech
│   ├── ingestion.py             # Document processing + embedding
│   ├── store.py                 # SQLite + vector store
│   └── config.py                # API keys, model settings
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

---

## Evaluation

| Dimension      | Method                                                     |
| -------------- | ---------------------------------------------------------- |
| **Accuracy**   | LLM-as-judge: any claims not supported by sources?         |
| **Coverage**   | LLM-as-judge: key points missed?                           |
| **Engagement** | Human eval: pleasant to listen to?                         |
| **Usefulness** | Human eval: would you listen to this daily?                |

---

## Open Tradeoffs

- **Streaming vs. batch audio** — streaming is better UX, batch is simpler to start
- **Single combined audio vs. per-topic segments** — combined is natural; per-topic allows skipping
- **HN content fetching** — HN API gives titles + URLs; article scraping may hit blocks
- **Conversation window size** — full session is simplest; token limits may require truncation
