# RoleLens

*See your resume through the lens of any role.*

> ✍️ **Write this (2–3 sentences, your voice):** what RoleLens is and who it's for. Use the lens
> metaphor here once (the job description is the lens; your resume is what you look at through it;
> the same resume looks different through each role) and never again.

**Live app:** https://rolelens-demo.onrender.com (uploads enabled; shared workspace with temporary storage).

| Chat with citations | Fit dashboard | Prompt injection refused |
|---|---|---|
| ![Chat](docs/screenshots/chat-citations.png) | ![Fit dashboard](docs/screenshots/fit-dashboard.png) | ![Injection](docs/screenshots/injection-refused.png) |

## What it does

- **Upload** one resume and any number of job descriptions (PDF, DOCX, TXT). Each is parsed, split
  into sections, given an auto-label like *Job #2 — Machine Learning Engineer, Lumen Labs*, and indexed.
- **Ask questions** ("What does Job #2 require that I'm missing?", "Which role fits me best?").
  Answers stream token by token and cite their sources as numbered pills that open the exact excerpt.
  When the documents don't contain the answer, it says so.
- **Fit dashboard:** per job, a 0–100 score, matched / partial / missing requirements ranked by
  prominence, the resume evidence behind every match, and a one-line verdict; plus a comparison of all roles.
- **Guardrails:** document text is treated as data, never instructions. Uploads containing
  instruction-like text are flagged, and off-topic questions are declined.

## Scope (contract for this build)

In scope: one resume, many job descriptions; grounded Q&A with citations; a per-job fit dashboard.

Out of scope (see [What's next](#whats-next)): user accounts and multi-tenancy, multiple resumes,
conversation memory, reranking / hybrid search, an async ingestion queue, resume rewriting, job scraping.

## Setup

Needs Docker (with Compose v2), an Anthropic API key and an OpenAI API key.

```bash
git clone https://github.com/anitakapal25/rolelens.git
cd rolelens
cp .env.example .env          # then set ANTHROPIC_API_KEY and OPENAI_API_KEY in .env
docker compose up --build
```

Open **http://localhost:8080**. API docs: http://localhost:8000/docs. The first build takes about a
minute. Data survives restarts (named volumes); `docker compose down -v` wipes it.

No files of your own? Upload the fictional samples in
[`backend/app/eval/sample_docs/`](backend/app/eval/sample_docs/): one resume and three job
descriptions. The Brightwave one contains a prompt-injection attempt.

### Local development

Needs Python 3.12 and Node 22.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm install)
make chroma      # vector DB in Docker on :8001
make backend     # API on :8000 (reload)
make frontend    # UI on :5173
make test        # 151 offline tests (LLM, embeddings and vector DB are faked)
make eval        # golden-set eval against the real models (~$0.15)
```

### Render (free hosting)

The app runs as **one** container ([`Dockerfile.render`](Dockerfile.render)): the API under `/api`,
the built frontend at `/`, and an in-memory vector store. Optional demo mode (`DEMO_MODE=true`) loads
a pre-processed snapshot of
the sample documents ([`backend/app/demo/seed.json`](backend/app/demo/seed.json)), so it starts
with zero model calls. In demo mode, uploads are disabled; chat is limited to 15 questions per IP per hour and
200 per day.

- **Render**: New → Blueprint → this repo ([`render.yaml`](render.yaml)) → enter the two keys.
  The current service has `DEMO_MODE=false` to enable uploads. Data is lost when the free service
  sleeps or restarts, and all visitors share the same workspace.

## Architecture

```mermaid
flowchart LR
  B["Browser<br/>React + Vite + Tailwind"] -- "/api (REST + SSE)" --> N["nginx"]
  N --> A["FastAPI"]
  A --> R[("SQLite registry<br/>documents, chunks,<br/>extractions, fit cache")]
  A --> C[("Chroma<br/>vectors + metadata")]
  A -- "embeddings" --> O["OpenAI<br/>text-embedding-3-small"]
  A -- "route · extract · match" --> H["Claude Haiku 5.5"]
  A -- "grounded answers (stream)" --> S["Claude Sonnet 5.5"]
```

**Upload path:** parse (PyMuPDF / python-docx) → detect sections → chunk (one chunk per job/project
entry; long sections split on bullet boundaries with overlap) → one Haiku structured-extraction call
(skills, years, evidence) → embed chunks with a context header → write SQLite, then Chroma. Model
calls happen before any write, so a failed upload leaves nothing half-indexed.

**Question path:** route the question to documents (keyword rules for explicit references like
"Job #2", Haiku when unsure, all documents if the router fails) → search each routed document
separately with a metadata filter (top-k per job description; a small resume is included whole) →
build a prompt of numbered, labelled, escaped chunks → stream Sonnet's answer over SSE → send the
cited chunk numbers with the final event.

**Fit path:** Haiku judges match / partial / missing for each job requirement against the resume's
skills (cached per job and resume pair) → plain Python computes the weighted score, verdict and ranking.

Code map: `backend/app/{api, ingest, retrieval, llm, chat, fit, eval, demo}`, `frontend/src/{components, lib}`.
Every decision is logged in [`docs/decisions.md`](docs/decisions.md).

## RAG / LLM decisions

| Area | Considered | Picked | Gave up |
|---|---|---|---|
| LLM | One model for everything; GPT | **Claude Sonnet 5.5** for answers, **Haiku 5.5** for routing, extraction and matching | Single-vendor simplicity (embeddings are OpenAI) |
| Embeddings | Sentence-transformers locally; Voyage | **OpenAI `text-embedding-3-small`** (1536-d) | A second API key and vendor |
| Vector DB | pgvector, Pinecone, in-memory | **Chroma** (Docker, cosine, metadata filters); in-memory for the free demo | Managed scaling; SQL joins with the registry |
| Orchestration | LangChain, LlamaIndex | **Hand-rolled** (~200 lines: router, per-document search, one prompt builder) | Ready-made integrations; more code to own |
| Structured output | "Reply in JSON" + parsing | **Claude structured outputs** into Pydantic models | Nothing significant |

> ✍️ **Write this: why retrieval at all?** The four sample documents total ~4k tokens, so they fit
> in Sonnet's context window. Explain why you still built retrieval, and what changed after measuring.
> Facts to use:
> - Routing keeps a Job #2 answer from citing Job #1 *by construction* (a metadata filter), not by hoping.
> - Numbered, labelled chunks make `[n]` citations precise and checkable.
> - It scales to 20 JDs or a long CV without a redesign; prompts are 1.4k–4k tokens instead of everything every time.
> - Measured against it: top-k *inside the resume* dropped evidence twice (a stakeholder-facing role in M5; the current role in M8: "Where do I currently work?" ranked it 8th of 10). So a resume of ≤ 12 chunks is now sent whole (+~1k tokens, ≈ $0.002 per question). Retrieval still selects which JDs and which parts of them.

## Key technical decisions

**Section-aware chunking.** Headers are matched against per-document-type synonym tables
("Technical Skills", "AI PROJECTS", "Roles & Responsibilities", "Required Skills"), so "Skills" means
the candidate's skills in a resume and the employer's requirements in a JD. Each job and project
becomes its own chunk, tagged with company and role; oversized sections split on paragraph → bullet
→ line → sentence boundaries with ~200 characters of overlap. Chunk size (1,200 characters) was
chosen from the data: real resume entries are 300–600 characters.

**Document-filtered retrieval.** Every chunk carries `doc_id`, `doc_type`, `section`, `company`,
`role` and `entry`. Questions are routed first, then each routed document is searched separately,
so a long JD can't crowd out the resume. A distance cut-off drops weak matches but always keeps the
best chunk of every routed document.

**Structured extraction alongside RAG.** Chat uses retrieval over chunks; the dashboard uses one
cached extraction per document and one cached matching call per (job, resume) pair. The model makes
small, evidence-backed judgments (referencing skills by number, never free text), and code does all
the arithmetic: weight = core 3 / supporting 2 / minor 1, halved for preferred; credit = 1 / 0.5 / 0.
Years of experience are computed in code from the dated roles, not by the model.

> ✍️ **Write this (2–3 sentences per decision):** why each choice beats the obvious alternative
> (a fixed-size splitter, global top-k, asking the LLM for a score), and what it costs you. Draw on
> the M3, M5 and M7 entries in [`docs/decisions.md`](docs/decisions.md).

## Evaluation

`make eval` runs a committed golden set on fictional documents (reproducible by anyone);
`make eval-private` runs a gitignored set on my real resume and job descriptions. Both ingest into
a throwaway registry and their own Chroma collection, call the real models, and grade deterministically:
the exact routed documents, required facts (groups of alternatives), banned phrases, which documents
are cited, "not in your documents" / off-topic phrasing, and fit-score bands.

| Set | Cases | Result | Cost per run |
|---|---|---|---|
| Sample (committed): 16 Q&A incl. 3 "not in your resume", 2 prompt-injection, 2 off-topic + 3 fit bands | 19 | **16/16 Q&A, 3/3 fit** on the final run | ~$0.14 |
| Private (my documents): 14 Q&A + 3 fit bands | 17 | **14/14 Q&A, 3/3 fit** | ~$0.14 |

Sample-set history: **11/16 → 16/16 → 15/16 → 16/16**. Of the first five failures, two were my YAML
(an unquoted `Job #2` is cut at the `#` comment), two were grader phrase lists, and one was a real
retrieval bug (the current role was missing from context; fixed as described above). The 15/16 run
failed a grader on an answer that *quoted* the injected claim while refusing it. Fit scores also
vary between fresh matching runs (one sample job scored 54, 59 and 44), which is why fit checks are bands.
The latest report is in [`backend/app/eval/results/sample-latest.json`](backend/app/eval/results/sample-latest.json).

> ✍️ **Write this: the honest eval paragraph.** Report the real numbers, what failed and why, what
> you fixed in the app vs. in the eval, the limits (substring graders can't tell quoting from
> complying; 30 cases is small; one run is one sample of a stochastic system), and what you'd add
> (an LLM judge for faithfulness and injection cases; majority-vote matching).

## Productionizing (on Render)

> ✍️ **Draft outline, so rewrite the reasoning in your own voice.** The free demo already runs on
> Render; this is what a real multi-user version would change.

| Concern | Today | Production on Render |
|---|---|---|
| Compute | One container / Compose on one host | Render **Web Service** (Standard plan) running `app.main`, 2+ instances with autoscaling; nginx replaced by Render's managed TLS and proxy |
| Registry + vectors | SQLite + Chroma | **Render Postgres** with the **pgvector** extension: one database, `WHERE doc_id = …` filters in SQL, point-in-time recovery |
| Original files | Not kept | Object storage (e.g. S3 or Cloudflare R2), encrypted, with a retention policy |
| Ingestion | Synchronous in the request | Upload returns `202`; a Render **Background Worker** processes a job from a **Render Key Value** (Redis-compatible) queue; the UI shows progress |
| Auth + tenancy | None, one shared workspace | An identity provider (e.g. Auth0 or Clerk) issuing JWTs verified in a FastAPI dependency; `tenant_id` on every row and vector, enforced with Postgres row-level security |
| Secrets | `.env` | Render **environment groups** per environment; separate, rotated API keys for staging and production |
| Rate limits + caching | In-memory, per process | Shared counters and per-user quotas in Key Value; cache question embeddings and fit results |
| Observability | JSON logs, `/metrics`, `/health` | Render log streams to Better Stack or Datadog; OpenTelemetry traces with LLM spans (e.g. self-hosted Langfuse as a private service); alerts on `degraded` health, error rate and daily cost |
| CI/CD | GitHub Actions (tests, build, Docker) | Render deploys only after CI passes; **preview environments** per PR; nightly `make eval` as a Render **Cron Job** that fails on a pass-rate drop |
| Cost controls | Rate limit + provider spend caps | Per-tenant token budgets, prompt caching for the static system prompts, Haiku for cheap steps, `max_tokens` caps, budget alerts |
| Privacy | Local only | Encryption at rest (Render Postgres), a delete-my-data endpoint, data-retention limits, provider data-retention settings |

## Standards followed and skipped

**Followed**
- Layered backend (`api` → `ingest` / `retrieval` / `llm` / `fit`); route handlers hold no business logic.
- Type hints everywhere; Pydantic at every boundary (HTTP, LLM output, eval files, demo seed).
- All prompts in one file; document text delimited and escaped in every prompt.
- 151 offline tests (LLM, embeddings and vector DB faked through protocols); CI on every push; a golden-set eval for behaviour.
- Structured JSON logs with request ids, `/health` with dependency checks, `/metrics`.
- Atomic ingestion, a versioned match cache, an additive schema migration, a non-root container user, secrets only in env.
- A decision log kept during the build ([`docs/decisions.md`](docs/decisions.md)) and small commits.

**Skipped (deliberately, for a one-day build)**
- No authentication, no multi-tenancy; one shared workspace.
- Rate limiting only in the public demo, in memory, per process.
- SQLite registry: one backend instance only.
- No frontend unit tests (the UI was checked with scripted browser runs).
- No reranking or hybrid keyword search; no conversation memory.
- No LLM tracing tool (Langfuse); JSON logs carry the same fields.
- Backend image is 770 MB (PyMuPDF and Chroma client dependencies).

## AI tool usage

Built with Claude Code. [`CLAUDE.md`](CLAUDE.md) is the rules file every session starts from: fixed
stack (no LangChain), layer boundaries, Pydantic at boundaries, **no new dependency without asking**,
tests for every pure function in `ingest/` and `retrieval/`, all prompts in `llm/prompts.py`, and
eval rules (run `make eval` after prompt or retrieval changes; read failing answers before calling
them app bugs). The "AI workflow" section of [`docs/decisions.md`](docs/decisions.md) records how it was used.

> ✍️ **Write this: your do's and don'ts.** Be specific and honest about who wrote what. Facts:
> - The assistant wrote most of the code, including the core logic (answer prompt, router, per-document
>   search). That was your choice, so you could study it; you reviewed it and can explain each rule.
> - Dependencies were proposed and approved one by one.
> - Real-data checks drove most fixes: label truncation, the job-number race, matching generosity, null
>   years from extraction, YAML `#` comments, resume retrieval misses, the eager OpenAI client that broke CI.
> - What you kept for yourself: this README's reasoning, which questions go in the eval, which trade-offs to accept.

## What's next

- **LLM judge** for faithfulness and prompt-injection eval cases (the substring graders' known blind spot); a larger golden set built from real questions.
- **Stabler fit scores:** majority vote over three matching calls, or a fixed skill taxonomy; score soft skills separately.
- **Hybrid search + reranking** for long or many job descriptions.
- **Conversation memory** for follow-ups ("and what about Job #1?").
- **Accounts and multi-tenancy** (see Productionizing), then multiple resume versions.
- **Async ingestion** with progress events instead of a 5–25 s request.
- **Frontend tests** (SSE parser, citation rendering) and a smaller backend image.
- **Resume rewriting suggestions** per job, grounded in the gap list.
