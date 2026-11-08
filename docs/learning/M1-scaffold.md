# M1 — Scaffold & scope

## What we built
| File / dir | Purpose |
|---|---|
| `backend/app/{api,ingest,retrieval,llm,eval}/` | One package per layer of the request path |
| `backend/tests/` | pytest suite (filled from M3) |
| `frontend/src/{components,lib}/` | React UI pieces vs. non-UI helpers (API client, types) |
| `.gitignore` | Keeps `.env`, venvs, `node_modules`, local DBs out of git |
| `.env.example` | Every config key the app reads, with no secret values |
| `docs/decisions.md` | Running log: chose X, rejected Y, because Z |
| `README.md` | Stub with scope contract and empty section headings |

## Why this approach

### 1. Layout by *layer*, mirroring the request path
A question travels: **api** (HTTP in) → **retrieval** (route + search) → **llm** (prompt + generate) → back out.
Documents travel: **api** → **ingest** (parse + chunk) → **retrieval** (embed + store).
`eval` sits beside them and calls the same functions the API calls.

Rejected:
- **Flat `app/` with `main.py`, `utils.py`** — fine for 200 lines; by hour 6 everything lands in `utils.py` and route handlers grow business logic you can't unit-test.
- **Layout by feature (`chat/`, `documents/`, `dashboard/`)** — good for big teams, but here features *share* the same pipeline (the dashboard and chat both use ingestion output), so layer boundaries are the more natural seams.

Rule this sets up: **routes are thin**. A route parses the request, calls a service function, returns a Pydantic model. Logic lives in `ingest/`, `retrieval/`, `llm/` — which is exactly what makes it testable without an HTTP server.

### 2. Scope contract written *before* code
The README lists what is in scope and, just as importantly, what is out. Two benefits:
- When you're tempted mid-build ("I could add reranking…"), the list says no.
- The out-of-scope list becomes your "What's next" section for free — it shows you *thought* about those things and chose not to build them.

### 3. Secrets hygiene from commit #1
`.env` is in `.gitignore` *before* any file containing a key exists. If a key is ever committed, deleting it later isn't enough — it lives in history forever (and bots scan public GitHub for keys within minutes). `.env.example` documents every variable so a reviewer can `cp .env.example .env` and fill in two keys.

### 4. Git history as evidence
The empty first commit + small commits every 20–30 minutes show *process*. Reviewers read history to see whether a submission was built incrementally or dumped in one go.

### 5. Python 3.12, not your system 3.14
Your machine has Python 3.14. Libraries with compiled parts (PyMuPDF, chromadb's deps) often ship wheels for a new Python months after release, so `pip install` may try to compile from source and fail. 3.12 is mature and matches the Docker image (`python:3.12-slim`), so "works on my machine" = "works in Docker".

## Concepts / skills to learn
- **Separation of concerns** — each module answers one question ("how do I parse a PDF?", "which chunks are relevant?").
- **12-factor config** — config comes from environment variables, not code. Same image runs locally and in prod with different env.
  ```bash
  # .env.example
  CHAT_MODEL=claude-sonnet-5-5
  FAST_MODEL=claude-haiku-5-5
  TOP_K_PER_DOC=4
  ```
  Even model names are config: swapping models shouldn't need a code change.
- **`__init__.py`** — makes a directory an importable Python package (`from app.ingest.chunking import ...`).
- **`.gitignore` negation** — `.env.*` ignores `.env.local` etc., `!.env.example` re-includes the template.

## How to verify it yourself
```bash
cd ~/Documents/rolelens
git log --oneline            # empty initial commit + scaffold commit
tree -a -I .git              # or: find . -path ./.git -prune -o -print
git check-ignore -v .env     # should print the .gitignore rule that ignores it
```

## Interview questions you should be able to answer
1. **Why not put logic in route handlers?** Can't unit-test it without HTTP, can't reuse it from the eval runner, and it couples transport to behaviour.
2. **A key got committed. What do you do?** Rotate the key immediately (assume it's compromised), then rewrite history (`git filter-repo`) — rotation is the part that actually matters.
3. **Why write out-of-scope items down?** Prevents scope creep and turns omissions into deliberate, documented decisions.
4. **Why are model names in `.env`?** Config vs. code: you can A/B or downgrade a model for cost without a deploy.

## Further reading
- The Twelve-Factor App — "Config": https://12factor.net/config
- GitHub docs — "Removing sensitive data from a repository"
