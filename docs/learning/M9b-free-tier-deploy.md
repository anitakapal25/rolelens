# M9b — Free-tier deployment (Render public demo)

## What we built
| File | Purpose |
|---|---|
| `Dockerfile.render` | One image: Node builds the frontend → Python serves API + static files |
| `render.yaml` | Render Blueprint: free web service, health check, env vars (keys prompted, never in git) |
| `.dockerignore` (root) | Keeps `.env`, `samples/`, `.git`, local DBs out of the build context |
| `backend/app/serve.py` | `create_serving_app()`: API mounted at `/api`, Vite build at `/` |
| `backend/app/retrieval/store.py` → `MemoryStore` | In-process cosine-similarity store, same protocol as `ChromaStore` |
| `backend/app/demo/seed.py` + `seed.json` | Build/export/load a snapshot of the processed sample documents |
| `backend/app/demo/limits.py` | `RateLimiter` (per IP per hour + per day), `require_writable`, `client_ip` |
| `backend/app/main.py` | `/config` endpoint; demo start-up (seed + limiter) when `DEMO_MODE=true` |
| `frontend` | Demo banner; upload areas, rename and delete hidden when `config.demo` |
| Tests | 151 total. New: MemoryStore, rate limiter, seed contents, seed loading, read-only 403s, 429s, single-service mounting |

## Why this approach

### 1. Choosing the platform
| Option | For | Against |
|---|---|---|
| **Render free** (chosen) | Deploy from GitHub, HTTPS included, no server to manage | Sleeps after 15 min (~1 min cold start), **no disk**, 512 MB RAM, no private services on free |
| Oracle Always Free VM | Runs `docker-compose.yml` unchanged, real disk, no sleep | You manage a Linux server (updates, firewall, TLS) |
| GCP e2-micro / AWS t3.micro | Real VM | 1 GB RAM is tight for 3 containers; AWS free tier is now time-limited credits |

Render's constraints shaped everything below. The good habit to name: **the platform's limits are design inputs**, not something to fight.

### 2. Three services became one
On the free plan only public web services are available. Running Chroma as its own public service would put the **vector database on the internet**, readable and writable by anyone. So for the demo:
```
browser ──► Render (one container)
            ├── /api/*  → FastAPI app (create_app)
            └── /*      → StaticFiles(dist/, html=True)
```
`app/serve.py` mounts the existing app under `/api`, so no route changed. The frontend is built with `VITE_API_BASE_URL=/api`, exactly as behind nginx in Compose. Same origin means no CORS.

### 3. No disk, so a seed instead of a database
Every time the service sleeps and wakes, the container starts fresh: nothing written to disk survives. Options:
- **Re-ingest the samples on every start:** about $0.005 and 30 s per wake-up, and fit scores would **drift** between wake-ups (matching variance from M7).
- **Commit a pre-processed snapshot (chosen):** `python -m app.demo.seed build` ingests the four fictional documents once with real models, computes the fit matches, and writes text, chunks, extractions, **embeddings** and **fit matches** to `seed.json` (660 KB). On start-up `load_seed()` inserts them. **Zero model calls, about a second, identical scores every time.**

The seed is built *only* from `app/eval/sample_docs/`, and a test checks the exact file list. Your real resume can't end up in it.

**`MemoryStore`:** 22 vectors don't need a vector database. A dict plus cosine similarity (`dot / (|a|·|b|)`) is enough, and it implements the same `VectorStore` protocol, so retrieval code doesn't know the difference. That's the payoff of the protocol design from M4: swapping the storage backend changed **one line** in `build_services`.

**A subtle bug caught before deploy:** `app/serve.py` imports `app.main`, which creates its own app at import, so two app instances start in one process. The first fills the SQLite registry; the second saw "registry not empty", skipped seeding, and was left with an **empty** in-memory store. Fix: check the registry and the store **separately** (tested).

### 4. Protecting a public demo without a password (your choice)
| Risk | Control |
|---|---|
| Strangers uploading personal data | Read-only: upload/rename/delete/reindex → **403** with a friendly message; UI hides those controls |
| Someone running up your API bill | **15 questions per IP per hour** + **200 per day overall** → worst case about $2–3/day |
| Fit dashboard costs | Served from seeded matches, no model calls |
| Prompt injection | The seeded Brightwave JD *contains* one, so visitors can watch it being refused |

The client IP comes from `X-Forwarded-For` (Render's proxy sets it; the first entry is the real client). The limiter lives in memory per process, which is correct for one free instance; several replicas would need a shared store (Redis). **Also set monthly spend limits in the Anthropic and OpenAI consoles.** That's the only control that holds even if everything else fails.

### 5. Secrets and build-context hygiene
`Dockerfile.render` builds from the repo root, so `docker build` would send *the whole folder* (including `.env` with your keys and `samples/` with your resume) to the builder unless excluded. The root `.dockerignore` excludes them, and this was **verified** with a throwaway build that lists the context. API keys reach the service only as Render environment variables (`sync: false` in `render.yaml` makes Render prompt for them; they're never in git or in the image).

### 6. Verified the way Render runs it
`docker run --memory 512m --env-file <keys only>` with no volume:
- start-up log: `"msg": "demo mode", "seeded_documents": 4, "vector_store": "memory"`
- memory: **143 MB / 512 MB**
- `/api/health` ok · `/` serves the app · upload → 403 · chat streams (first token 1.6 s) · fit 78/60/37 from the seed · 16th question from one IP → **429** "Demo limit: 15 questions per hour".

## Concepts / skills to learn
- **Platform constraints as requirements:** sleep, disk, memory and networking decide the architecture.
- **Same app, different composition:** Compose (nginx + API + Chroma) and Render (one process, memory store) share 100% of the business code; only wiring and env vars differ.
- **Snapshotting expensive work:** precompute deterministic artefacts (embeddings, model judgments) once and ship them.
- **Rate limiting:** sliding window per key plus a global budget; reject without counting; tell the user when to retry.
- **Build context:** everything in the context is uploaded to the builder; `.dockerignore` is a security control, not just a speed-up.

## Deploy it (your steps)
1. **Set spend limits first:** Anthropic Console → Billing → limits; OpenAI → Settings → Limits (e.g. $10/month each).
2. Sign up at **render.com** with GitHub, and allow access to `anitakapal25/rolelens`.
3. Dashboard → **New → Blueprint** → choose the repo → Render reads `render.yaml`.
4. Paste `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` when prompted → **Apply**.
5. Wait for the first build (~5–8 min on free). Open `https://rolelens-demo.onrender.com` (or the URL Render shows).
6. Check: `https://<your-url>/api/health` → `"documents": 4`. Ask a suggested question.

Every push to `main` redeploys automatically (`autoDeploy: true`). If you change extraction, chunking, the embedding header or the matching prompt, rebuild the seed first: `cd backend && ../.venv/bin/python -m app.demo.seed build`.

## Known limitations
- Cold starts take about a minute after 15 idle minutes. Fine for a portfolio demo, but mention it to reviewers.
- Rate limits reset when the instance restarts, so the daily cap is per instance lifetime, not strictly per day.
- The demo can't show uploads; reviewers who want that run it locally (the README Setup).

## Interview questions you should be able to answer
1. **How did you deploy three services on a free tier?** One container: the API at `/api` and static files at `/`, with an in-memory vector store. A public Chroma would expose the data, and the free tier has no private networking.
2. **No disk: how does it keep its data?** It doesn't need to. A committed snapshot of the processed sample documents loads at every start, with zero model calls and identical results.
3. **How do you stop a public demo from costing a fortune?** Read-only, per-IP and global rate limits, seeded fit scores, and provider spend limits as the backstop.
4. **What would change for a real multi-user deployment?** Auth, a managed vector DB and Postgres, Redis-backed rate limits, per-tenant isolation (see Productionizing in M10).
5. **How do you keep secrets out of images?** `.dockerignore` for the build context, env vars at runtime, `sync: false` in the Blueprint, and a context-listing check.

## Further reading
- Render docs — Blueprints (`render.yaml`), free instance limits, Docker deploys
- FastAPI docs — "Sub applications – Mounts", `StaticFiles`
- OWASP — "Denial of Wallet" (cost-exhaustion attacks on pay-per-use APIs)
