# CLAUDE.md — rules for AI-assisted work on RoleLens

RoleLens: upload one resume and several job descriptions, ask grounded questions with citations, and see a fit dashboard for each job.
These rules hold for every AI assistant session in this repo. If a rule and a request conflict, ask before acting.

## Stack (fixed; do not suggest alternatives)
- **Backend:** Python 3.12, FastAPI, Pydantic v2, pydantic-settings, Uvicorn. Streaming over SSE (`text/event-stream`).
- **LLM:** Anthropic SDK called directly. `CHAT_MODEL` (claude-sonnet-5-5) for answers, `FAST_MODEL` (claude-haiku-5-5) for routing and extraction. Model names come from config, never hard-coded.
- **Embeddings:** OpenAI `text-embedding-3-small`.
- **Vector DB:** Chroma server (Docker) used through the HTTP client.
- **Doc registry:** SQLite through the stdlib `sqlite3` module (no ORM).
- **Parsing:** PyMuPDF (PDF), python-docx (DOCX), plain read for TXT.
- **Frontend:** Vite, React 18, TypeScript, Tailwind CSS. No SSR, no state library, no UI kit.
- **Orchestration:** hand-rolled. **No LangChain, LlamaIndex, or agent frameworks.**
- **Infra:** Docker Compose with three services (backend, frontend, chroma).

## Structure
```
backend/app/
  main.py         FastAPI app factory, router registration
  config.py       Settings (pydantic-settings, reads .env)
  models.py       Pydantic models shared across layers
  api/            Route handlers ONLY: validate input, call a service, return a model
  ingest/         parse.py, chunking.py, registry.py, extraction
  retrieval/      embed.py, store.py, router.py, search.py
  llm/            client.py (thin Anthropic wrapper), prompts.py (ALL prompt text)
  eval/           golden.yaml, run.py
backend/tests/    pytest, mirrors app/ (test_chunking.py, test_router.py, ...)
frontend/src/
  components/     React components, one per file
  lib/            api.ts (fetch + SSE), types.ts, helpers. No JSX here.
docs/decisions.md       decision log (chose / rejected / why)
docs/learning/          one learning doc per milestone
```
- **Business logic never sits in a route handler.** A handler is roughly 10 lines: parse, call, return.
- Dependencies point inward: `api` → `ingest`/`retrieval`/`llm`. Lower layers never import from `api`.
- Pass the Anthropic, OpenAI and Chroma clients in as arguments, or through FastAPI dependencies, so tests can swap in fakes.

## Style
- Type hints on every function signature, including return types.
- Pydantic models at every boundary: HTTP request and response bodies, LLM JSON output, Chroma metadata, eval files.
- **No bare `except`.** Catch specific exceptions, log with context, and re-raise or turn into an `HTTPException`.
- Errors the user sees are short and actionable. Stack traces go to the logs, never to the response.
- Logging uses the stdlib `logging` module with structured (JSON) output. No `print` in app code.
- Prefer small pure functions. Keep side effects (network, disk) at the edges.
- Frontend: function components with hooks, no `any`, Tailwind classes only (no CSS-in-JS).

## Dependencies
- **Never add a package (pip or npm) without asking first.** Say what it does and why the stdlib or an existing dependency is not enough.
- Pin versions in `backend/requirements.txt` and `frontend/package.json`.

## Tests
- Every pure function in `ingest/` and `retrieval/` ships with a test in the same change.
- Tests never call real APIs. Fake the LLM, embedding and Chroma clients.
- Run `pytest backend/tests` before saying a change is done. If tests fail, show the output.

## Prompts and LLM calls
- **All prompt text lives in `backend/app/llm/prompts.py`.** No prompt strings inline anywhere else.
- Retrieved document text is untrusted. Wrap it in clear delimiters and treat it as data, never as instructions.
- Answers cite chunk numbers inline as `[n]` and say plainly when the documents do not contain the answer.
- Structured outputs are parsed into a Pydantic model and validated. Malformed JSON is an error to handle, not to ignore.

## Hand-written by the developer, not generated
The AI assistant may review these and suggest changes, but it does not write them from scratch:
- `llm/prompts.py`: the answer prompt (`build_answer_prompt`)
- `retrieval/search.py`: per-document top-k and the scoring logic
- README reasoning paragraphs (RAG decisions, eval write-up, trade-offs)

## Secrets and git
- Never print, log or commit API keys. `.env` is gitignored, and `.env.example` holds names only.
- Commit as `anitakapal25 <anitakapal25@gmail.com>` (repo-local config).
- Small commits with real messages. At the end of each milestone, update `docs/decisions.md`, add `docs/learning/MN-*.md`, then commit and push.

## Process
- Every decision gets one line in `docs/decisions.md`: chose X, rejected Y, because Z.
- Scope is fixed by the README's scope contract. New ideas go to "What's next", not into the code.
