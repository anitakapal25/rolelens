# M9 — Tests & Docker

## What we built
| File | Purpose |
|---|---|
| `backend/Dockerfile` | `python:3.12-slim`, cached dependency layer, non-root user, `HEALTHCHECK` |
| `frontend/Dockerfile` | Multi-stage: `node:22-slim` builds → `nginx:1.27-alpine` serves |
| `frontend/nginx.conf` | Same-origin `/api` proxy, SSE unbuffered, SPA fallback, long cache for hashed assets |
| `backend/.dockerignore`, `frontend/.dockerignore` | Keep tests, caches, local DBs and `node_modules` out of the build context |
| `docker-compose.yml` | chroma + backend + frontend, health-gated startup, named volumes |
| `.github/workflows/ci.yml` | Offline tests, frontend build, `docker compose build` on every push |
| `README.md` → Setup | Copy-pasteable Docker and local-dev instructions |
| `docs/screenshots/` | Chat with citations, fit dashboard, injection refused, all on **fictional** sample data |

**Verified by a real clean-clone run:** `git clone` into a temp folder → `cp .env.example .env` → add two keys → `docker compose up --build`. Then, through `http://localhost:8080`: upload the 4 sample documents, chat (streamed), fit dashboard, injection warning plus refusal, and a restart with data intact.

## Why this approach

### 1. Three services, started in the right order
```yaml
backend:
  depends_on:
    chroma: { condition: service_healthy }
frontend:
  depends_on:
    backend: { condition: service_healthy }
```
A plain `depends_on` only waits for the container to *start*, not to be *ready*. Without health conditions the backend can hit Chroma before Chroma listens, and the first request fails. Each service has a healthcheck: a TCP probe for Chroma, and `GET /health` from inside the backend image. Result from the run: Chroma healthy → backend healthy → frontend started, all up in about 13 s (cached) or about 60 s (cold build).

### 2. Backend image: layers, size, user
```dockerfile
COPY requirements.txt .
RUN pip install -r requirements.txt      # cached until requirements.txt changes
COPY app ./app                           # code changes only rebuild from here
```
- **Layer order** is the most important Dockerfile skill: put what changes least first. A code edit rebuilds in seconds, not a minute.
- **Non-root user:** if the process were compromised, it isn't root in the container. `/data` (the SQLite volume) is owned by that user.
- **Size: 770 MB**, honestly large. Most of it is PyMuPDF and chromadb-client's dependencies (numpy, OpenTelemetry, …). Options for later: a builder stage producing wheels, or dropping `chromadb-client` for direct HTTP calls. Not worth it on day one.
- `.dockerignore` keeps `tests/`, `data/` and caches out, so your local SQLite file can never end up in an image.

### 3. Frontend image: multi-stage
| Stage | Base | Contains |
|---|---|---|
| build | `node:22-slim` | Node, `node_modules`, sources → `npm run build` → `dist/` |
| final | `nginx:1.27-alpine` | Only `dist/` + `nginx.conf` (**74 MB**) |

The final image has no Node, no dependencies and no source code: smaller, faster to pull, and less to attack.

**Why `node:22-slim`, not Alpine:** the first attempt on Alpine crashed in `npm ci`. Vite 8, Tailwind 4 and their bundler ship platform-specific native binaries, and the lockfile was resolved on glibc Linux, while Alpine uses musl. Matching the build OS to the lockfile's OS is the dependable fix.

### 4. nginx as the front door
```nginx
location /api/ {
    proxy_pass http://backend:8000/;   # trailing slash: /api/chat → /chat
    proxy_buffering off;               # stream SSE tokens immediately
    proxy_read_timeout 300s;           # long answers don't get cut off
    proxy_set_header X-Request-ID $request_id;
}
location / { try_files $uri /index.html; }
```
- **Same origin:** the browser talks only to `:8080`, and nginx forwards `/api/*` to the backend over Compose's internal network (`backend` is a DNS name there). No CORS in production, and reviewers need only one URL. The frontend is built with `VITE_API_BASE_URL=/api`.
- **SSE through a proxy:** nginx buffers responses by default, which would deliver the whole answer at the end. With `proxy_buffering off`, the measured first token arrived at 1.24 s and the answer finished at 5.27 s, across 120 separate token events.
- **Request ids end to end:** nginx generates `$request_id` and passes it on, the backend logs it on every JSON line and returns it, so one id traces a request from the proxy to the model call.

### 5. Configuration: one `.env`, two environments
`env_file: .env` provides keys and model settings; `environment:` in Compose **overrides** what must differ inside Docker (`CHROMA_HOST=chroma`, `REGISTRY_DB_PATH=/data/…`). So the same `.env` works for `make backend` (Chroma at `localhost:8001`) and for `docker compose up` (Chroma at `chroma:8000`). Keys never go into an image; they're injected at run time.

### 6. Data that survives restarts
Named volumes `chroma_data` (vectors) and `backend_data` (SQLite: documents, chunks, extractions, fit cache). Verified: `down` + `up` showed `documents: 4, indexed_chunks: 22`. `docker compose down -v` deletes them, which is how the clean-clone check cleaned up.

### 7. The clean-clone test (why it matters)
"Works on my machine" usually hides a file that exists only locally: a `.env`, an override, a cached image, the `samples/` folder. Cloning from GitHub into a new folder proves the repo *alone* is enough. The clone had no `samples/` and no override file; only `.env.example` became `.env` with two keys. The clone and its `.env` were deleted afterwards. The runbook calls a README whose setup doesn't work "the most common way a good submission loses points".

### 8. A real-world detour: Docker DNS
Builds first failed with "Temporary failure in name resolution". Your Docker daemon was configured (`/etc/docker/daemon.json`) with company DNS servers that don't answer off the company network, so every container, including build steps, couldn't resolve `pypi.org` or `registry.npmjs.org`. Two lessons:
- **Diagnose before patching:** comparing "host resolves in 0.5 s" with "container can't resolve" pointed straight at Docker's DNS, not at npm, IPv6 or the Dockerfile.
- **Don't commit machine-specific fixes:** a local override file and builder tricks were tried and removed, and the real fix (clearing `daemon.json`) was made on your machine, not in the repo.

### 9. CI
`.github/workflows/ci.yml` runs on every push:
1. **backend:** `pytest`. All 141 tests run offline, because the LLM, embeddings and Chroma are faked through the protocols from M4.
2. **frontend:** `npm run build`, the strict TypeScript check plus the bundle.
3. **docker:** `docker compose build`, so a broken Dockerfile is caught before a reviewer finds it.

The golden-set eval calls paid models, so it isn't in CI. It's a manual `make eval`, and the production answer is a scheduled job with a budget.

### 10. Test coverage vs. the runbook's list
| Runbook asks | Where |
|---|---|
| Chunking: sections, metadata, oversized splits | `test_chunking.py` (16) |
| Routing: "Job #2" → right ids; ambiguous → sensible fallback | `test_router.py` (19) |
| Retrieval filtering never returns excluded docs | `test_search_filter.py` |
| Prompt assembly: numbered chunks, labels, system rules | `test_prompts.py` |
| API integration with a mocked LLM | `test_api_chat.py`, `test_api_documents.py`, `test_api_fit.py` |
| (extra) atomic ingest, scoring, guardrails, observability, eval graders, concurrency | the rest of the 141 |

The honest gap: **no frontend unit tests** (no test runner added). The UI was verified with scripted browser runs instead.

## Concepts / skills to learn
- **Docker layer caching:** order instructions from least to most frequently changed.
- **Multi-stage builds:** build tools in one stage, only artefacts in the final image.
- **Readiness vs. liveness:** `service_healthy` waits for readiness, not just a started process.
- **Reverse proxy basics:** path-based routing, header forwarding, buffering and timeouts. Most "streaming doesn't work in production" bugs live here.
- **12-factor config in containers:** same image, different environment; secrets injected at run time.
- **Reproducibility checks:** the clean clone is the only real proof that setup instructions work.

## How to verify it yourself
```bash
docker compose up --build            # http://localhost:8080
docker compose ps                    # all three healthy
curl -s localhost:8080/api/health
curl -sN -X POST localhost:8080/api/chat -H 'content-type: application/json' \
     -d '{"question":"Which role fits me best?"}'           # tokens should trickle in
docker compose logs backend | grep '"msg": "answered"'      # JSON logs with request ids
docker compose down && docker compose up -d                 # data still there
docker compose down -v                                      # wipe everything
```
Try: comment out `proxy_buffering off;`, rebuild the frontend, and watch the answer arrive all at once.

## Known limitations
- Backend image is 770 MB.
- SQLite in a volume means **one backend replica** only. Scaling out needs Postgres (see Productionizing in M10).
- No TLS. In production it terminates at a load balancer or ingress.
- The frontend still has no unit tests.

## Interview questions you should be able to answer
1. **Walk me through `docker compose up`.** Chroma starts and passes its TCP healthcheck → the backend starts and `/health` passes → nginx starts. The browser hits `:8080`, and `/api` is proxied to `backend:8000` on the Compose network.
2. **Why put nginx in front instead of serving the frontend from FastAPI?** It separates static serving (cache headers, SPA fallback) from the API, gives one same-origin URL with no CORS, and mirrors production, where a proxy or CDN sits in front anyway.
3. **How did you make SSE work through the proxy?** Disable proxy buffering and extend the read timeout. Verified by timing the first token against the last.
4. **Why multi-stage for the frontend?** The final image ships only static files: 74 MB, no Node, no sources.
5. **How do you know a reviewer can run it?** A clean clone from GitHub into a new folder, with only the README steps, tested end to end, then torn down. CI also builds the images on every push.
6. **Tell me about a debugging problem.** Builds failing on name resolution. I compared host vs. container DNS, traced it to the daemon's corporate DNS config, fixed it on the machine, and kept it out of the repo.

## Further reading
- Docker docs — "Multi-stage builds", "Compose: control startup order", `.dockerignore`
- nginx docs — `proxy_buffering`, `proxy_read_timeout`
- The Twelve-Factor App — "Config", "Backing services"
