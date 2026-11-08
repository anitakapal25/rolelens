# RoleLens

*See your resume through the lens of any role.*

<!-- Opening paragraph: say the lens metaphor once, here, and never again. Write in your own voice. -->

> Status: under construction.

## Scope (contract for this build)

In scope:
- One resume, many job descriptions (PDF, DOCX, TXT)
- Grounded Q&A over those documents, with inline citations to source chunks
- A per-job fit dashboard: match score, matched skills with evidence, missing requirements, verdict

Out of scope (→ "What's next"):
- User accounts, auth, multi-tenant isolation
- Multiple resumes / resume versioning
- Conversation memory across sessions
- Reranking and hybrid (keyword + vector) search
- Async / streaming ingestion queue
- Resume rewriting or cover-letter generation
- Job scraping from URLs

## Setup

Needs Docker (with Compose v2), an Anthropic API key and an OpenAI API key.

```bash
git clone https://github.com/anitakapal25/rolelens.git
cd rolelens
cp .env.example .env          # then set ANTHROPIC_API_KEY and OPENAI_API_KEY in .env
docker compose up --build
```

Open **http://localhost:8080**. The API docs are at http://localhost:8000/docs.
First build takes about a minute; later starts take seconds. Data survives restarts
(named volumes); `docker compose down -v` wipes it.

To try it without your own files, upload the fictional samples in
[`backend/app/eval/sample_docs/`](backend/app/eval/sample_docs/): one resume and three job
descriptions (the Brightwave one contains a prompt-injection attempt).

### Local development (without Docker for the app)

Needs Python 3.12 and Node 22.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm install)
make chroma      # vector DB in Docker on :8001
make backend     # API on :8000 (reload)
make frontend    # UI on :5173
make test        # 141 offline tests
make eval        # golden-set eval against real models (~$0.15)
```

### Free public demo (Render)

A read-only demo runs as **one** free Render web service: [`Dockerfile.render`](Dockerfile.render)
serves the API under `/api` and the built frontend at `/`, with an in-memory vector store seeded
from the fictional sample documents ([`backend/app/demo/seed.json`](backend/app/demo/seed.json)),
so it starts without any model calls. Uploads are disabled and chat is limited to 15 questions per
IP per hour and 200 per day.

To deploy your own: Render dashboard → **New → Blueprint** → select this repo
([`render.yaml`](render.yaml)) → enter `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` → **Apply**.
The free plan sleeps after 15 minutes idle, so the first request after a pause takes about a minute.

## Architecture
_TODO_

## RAG / LLM decisions
_TODO — from docs/decisions.md_

## Key technical decisions
_TODO_

## Evaluation
_TODO (M8) — report the real pass rate_

## Productionizing
_TODO (M10)_

## Standards followed and skipped
_TODO_

## AI tool usage
_TODO — see CLAUDE.md and docs/decisions.md#ai-workflow_

## What's next
_TODO — start from the out-of-scope list above_
