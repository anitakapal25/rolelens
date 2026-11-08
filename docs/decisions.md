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

### M3 — Ingestion & chunking
- Section-aware chunking (header synonyms → canonical sections) over a fixed 500-char splitter — rejected blind splitting because it cuts a job's bullets in half and mixes "Requirements" with "Nice to have".
- Header **synonym maps** per doc type over exact keywords — real docs say "Technical Skills", "AI PROJECTS", "Roles & Responsibilities", "Required Skills"; and "Skills" means *my* skills in a resume but *their* requirements in a JD.
- One chunk per experience entry / project, tagged with company + role — rejected chunking the whole Experience section because a question about one employer would retrieve the others too.
- Oversized sections split on paragraph → bullet → line → sentence boundaries with ~200-char overlap — rejected token-window overlap because bullets are the natural unit of meaning in these docs.
- Chunk size 1200 chars (~300 tokens) — my real resume entries are 300–600 chars, so each job/project fits in one chunk; JDs get 1–2 chunks per section.
- SQLite registry stores documents **and** chunks; Chroma (M4) is a derived index — rejected in-memory dict because it's lost on restart; rejected Chroma-as-only-store because rename/delete/rebuild are easier with SQL.
- New resume replaces the old one — scope says one resume; rejected versioning.
- Default labels "Resume" / "Job #N"; job numbers never reused — "Job #2" must keep meaning the same document after a delete. M4 extraction will improve auto-labels.
- PyMuPDF over pdfplumber/pypdf — fastest and handles layout well; DOCX tables flattened to "a | b" rows.
- Validation: extension allow-list, 5 MB cap (reads at most cap+1 bytes), 10-page PDF cap, reject empty text (scanned PDFs).
- Test fixtures use a fictional resume — rejected using my real resume in tests so personal data stays out of git.

## AI workflow
How the AI assistant is used, kept as notes during the build.

**Rules:** `CLAUDE.md` fixes the stack, layout, style, test and dependency rules so every session starts from the same constraints.

**Handed to the assistant:** scaffolding, boilerplate (FastAPI wiring, Pydantic models, Dockerfiles), parsers, test cases, frontend components.

**Hand-written / owned by me:** the answer prompt (`build_answer_prompt`), per-document retrieval scoring, README reasoning.

**Refused to let it touch:** adding dependencies without asking, committing anything with my work email, writing the README's reasoning.

**Log** (add entries as they happen):
- M1: Assistant scaffolded the layout, env template and scope list from the runbook. _(Your note: what you changed or kept.)_
- M2: Assistant drafted `CLAUDE.md` from the runbook's rule list. _(Your note: what you changed after reviewing it.)_
