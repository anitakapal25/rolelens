# Decisions log

One line per decision: what was chosen, what was rejected, and why.
Raw notes — rewrite in your own words when turning these into the README.

## Locked stack

| Decision | Pick | Why |
|---|---|---|
| Option | 4 — Career Intelligence Assistant | I can judge answer quality myself with my own resume |
| Backend | Python + FastAPI, SSE streaming | Fastest path to a streaming API I can explain |
| Frontend | Vite + React + Tailwind | No SSR complexity, fast iteration |
| Vector DB | Chroma (Docker) | Zero-config, persists to disk, swappable |
| Embeddings | OpenAI `text-embedding-3-small` | Cheap, strong, 1536-dim |
| LLM | Claude (Sonnet for answers, Haiku for routing/extraction) behind a thin client | Shows orchestration without a framework; cheap model where quality matters less |
| Orchestration | Hand-rolled, no LangChain | Every step is visible and debuggable; fewer dependencies |

## Log

### M1 — Scaffold
- Layered layout (`api/ingest/retrieval/llm/eval`) over a flat `app/` — rejected flat because routes would end up holding business logic.
- `.env` gitignored before first real commit; `.env.example` lists every key — rejected committing a sample `.env` because it is too easy to fill in and push.
- Python 3.12 for the backend (local and Docker) — rejected system Python 3.14 because some wheels (PyMuPDF, chromadb) lag new releases.

### M2 — AI rules file
- `CLAUDE.md` at repo root over `.cursorrules` — rejected `.cursorrules` because I'm using Claude Code; any assistant can read a plain markdown file anyway.
- "Ask before adding a dependency" rule — rejected letting the assistant install freely because each feature tends to pull in a framework.
- SQLite via stdlib `sqlite3` for the registry — rejected SQLAlchemy/ORM as unnecessary for one table.
- Prompts centralised in `llm/prompts.py` — rejected inline f-strings because prompts are code I need to review, diff and test.

## AI workflow
How the AI assistant is used, kept as notes during the build.

**Rules:** `CLAUDE.md` fixes the stack, layout, style, test and dependency rules so every session starts from the same constraints.

**Handed to the assistant:** scaffolding, boilerplate (FastAPI wiring, Pydantic models, Dockerfiles), parsers, test cases, frontend components.

**Hand-written / owned by me:** the answer prompt (`build_answer_prompt`), per-document retrieval scoring, README reasoning.

**Refused to let it touch:** adding dependencies without asking, committing anything with my work email, writing the README's reasoning.

**Log** (add entries as they happen):
- M1: Assistant scaffolded the layout, env template and scope list from the runbook. _(Your note: what you changed or kept.)_
- M2: Assistant drafted `CLAUDE.md` from the runbook's rule list. _(Your note: what you changed after reviewing it.)_
