# M3 — Ingestion & section-aware chunking

## What we built
| File | Purpose |
|---|---|
| `backend/app/config.py` | `Settings` via pydantic-settings: reads `.env`; keys are `SecretStr` |
| `backend/app/models.py` | `Chunk`, `DocumentSummary`, `RenameRequest`: the shapes that cross boundaries |
| `backend/app/ingest/parse.py` | PDF/DOCX/TXT → normalized text; upload validation errors |
| `backend/app/ingest/chunking.py` | Section detection, entry splitting, size control (pure functions) |
| `backend/app/ingest/registry.py` | SQLite store for documents and chunks |
| `backend/app/ingest/service.py` | `ingest_document()`: the use case that ties parse → chunk → store together |
| `backend/app/api/documents.py` | Thin routes: `POST/GET /documents`, `GET /documents/{id}/chunks`, `PATCH`, `DELETE` |
| `backend/app/main.py` | `create_app()` factory, error → HTTP mapping, CORS, `/health` |
| `backend/tests/` | 30 tests: chunking (16), parsing (8), API (6) |

Result on your real documents:
```
Resume  2 pages 11 chunks  contact 1 | summary 1 | skills 1 | projects 3 | experience 4 | education 1
Job #1  6 chunks  overview | responsibilities ×2 | success_measures | requirements | preferred
Job #2  4 chunks  overview | responsibilities | requirements | preferred
Job #3  4 chunks  overview | responsibilities | requirements | preferred
```
Each experience chunk carries `role` and `company`, e.g. `FullStack Developer | Zitro`, and each project chunk carries `entry`, e.g. `RecallGuard - Conversational Memory & Semantic Retrieval`.

## Why this approach

### 1. Why section-aware chunking beats a fixed-size splitter
A fixed 500-character splitter knows nothing about meaning. On a job description it will:
- cut a bullet in half ("5+ years of Pyth" / "on"),
- put the end of *Requirements* and the start of *Nice to have* in one chunk, so the model can't tell a must-have from a bonus,
- glue the end of your Zitro job onto the start of your Simplify job, so a question about Zitro pulls in Simplify facts.

Documents like resumes and JDs already have structure: headers and bullets. Using it gives chunks that are **about one thing**, and that is what makes retrieval precise.

### 2. Synonym maps, not exact keywords
The runbook listed `EXPERIENCE`, `SKILLS`, `REQUIREMENTS` and so on. Your real files say "Technical Skills", "AI PROJECTS", "Primary Responsibilities:", "Roles & Responsibilities", "Required Skills", "Preferred". So every header is normalized (lowercased, trailing colon removed, `&` → `and`) and looked up in a table that maps synonyms to one **canonical** name:
```python
match_header("Roles & Responsibilities", "job")  # -> "responsibilities"
match_header("Skills", "resume")                 # -> "skills"
match_header("Skills", "job")                    # -> "requirements"
```
The last two lines show why there's **one map per doc type**: in a JD, "Skills" are *their requirements*, not *your skills*. Canonical names matter later. The fit dashboard and the prompt can say "this came from the job's *requirements*" whatever the original header was.

Safety net: an unknown short ALL-CAPS line (e.g. `VOLUNTEERING`) still counts as a header.

### 3. One chunk per job / project (entry splitting)
Inside Experience, a new entry starts at a line like `Software Engineer | Simplify Workforce Pvt. Ltd.` followed by a date range on the next line. The date-range check is what stops `Live demo | Python, FastAPI` from being mistaken for a job. Which side is the role? Whichever part contains a role word (engineer, developer, lead…).

Why it matters: "What did I do at Zitro?" can now be answered from exactly one chunk, and the citation shows `experience · FullStack Developer | Zitro`.

### 4. Size control: natural boundaries + overlap
Most sections fit in one chunk (max 1200 chars ≈ 300 tokens). When one doesn't (Job #1's responsibilities), `split_text` breaks it into the **largest natural units that fit**:

> paragraph → bullet item → line → sentence → hard cut (last resort)

It then packs the units greedily into chunks and repeats a short **tail (≤ 200 chars)** of the previous chunk at the start of the next one. Overlap means a fact that sits on a boundary is fully present in at least one chunk.

Why 1200 chars? Your resume entries are 300–600 chars, so each one fits whole. Too small and an entry gets split; too large and a chunk covers several topics, so its embedding becomes an average of unrelated things and matches nothing well.

### 5. Normalization first
PyMuPDF writes each `•` on its own line, followed by the bullet text. `normalize_text` joins them into `• text`, turns every bullet glyph into `•`, collapses spaces and blank lines, and replaces curly apostrophes. Every rule after this can then assume one consistent format. Clean input makes simple regexes reliable.

### 6. SQLite registry as source of truth; Chroma will be an index
- **Rejected in-memory dict:** lost on every restart.
- **Rejected Chroma as the only store:** a vector DB is optimized for similarity search, not for "rename this doc", "list all jobs" or "delete and cascade". Storing chunks in SQLite means the Chroma index can be **rebuilt** at any time, e.g. after changing the embedding model.
- stdlib `sqlite3`, no ORM: two tables don't justify a dependency. `ON DELETE CASCADE` removes chunks with their document.

### 7. Labels and job numbers
Labels default to `Resume` / `Job #N`. Job numbers are `MAX + 1` and never reused, so "Job #2" keeps meaning the same document after you delete Job #1. That matters because users will type "Job #2" into chat (M5 routing). Renaming sets `label_is_custom`, so M4's auto-label (title + company from extraction) won't overwrite a name you chose.

### 8. Thin routes + a service function
```python
# api/documents.py: transport only
data = await file.read(settings.max_upload_bytes + 1)
return ingest_document(registry, settings, file.filename or "upload", data, doc_type, label)
```
`ingest_document` knows nothing about HTTP; the parser raises `FileTooLarge`, not a 413. `main.py` maps error types to status codes in one place. The same service can be called from a script or the eval runner. Reading at most `cap + 1` bytes means a 2 GB upload can't fill memory.

## Concepts / skills to learn
- **Chunking strategies:** fixed-size, recursive (split on separators in priority order, which is what `_units` does), structure-aware (headers), semantic (split where embeddings change). We combine structure-aware with recursive.
- **Metadata filtering:** the metadata on each chunk (`doc_id`, `section`, `company`) is what lets M5 search *only* Job #2 + resume. Retrieval quality depends on metadata as much as on embeddings.
- **Pure functions and testability:** `chunking.py` does no I/O. Tests pass a string in and check the chunks that come out, with no server, database or API key.
- **App factory pattern:** `create_app(settings)` lets tests build an app with a temp database (`tmp_path`) instead of touching your real one.
- **`SecretStr`:** `print(settings)` shows `**********` instead of your key.
- **Pydantic at boundaries:** `doc_type: Literal["resume","job"]` means `cover_letter` is rejected with a 422 before any of our code runs.

## How to verify it yourself
```bash
cd ~/Documents/rolelens/backend
../.venv/bin/python -m pytest -q                       # 30 passed

../.venv/bin/uvicorn app.main:app --reload --port 8000
# in another terminal:
curl -s -F file=@../samples/job2.txt -F doc_type=job localhost:8000/documents | python -m json.tool
curl -s localhost:8000/documents | python -m json.tool
curl -s localhost:8000/documents/<doc_id>/chunks | python -m json.tool
# Or open http://localhost:8000/docs for the interactive Swagger UI.
```
Things to try:
1. Upload `job1.txt`. Find which chunk boundary falls inside *Responsibilities* and spot the overlapping lines.
2. Change `CHUNK_MAX_CHARS=400` in `.env`, re-upload the resume and see how entries split.
3. Write a JD whose header is "What You'll Bring". It lands in `overview`. Add it to `JOB_SECTIONS` and add a test.

## Known limitations (honest list for the README)
- Header detection is regex/synonym based. An unusual header ("Your toolbox") is treated as content of the previous section.
- Entry detection expects `Role | Company` + a date range. A resume with "Company, City" on one line and the role on the next won't get company/role metadata. It still chunks fine, just without those tags.
- Two-column PDF resumes can come out of PyMuPDF with columns interleaved.
- Scanned PDFs (images) are rejected, not OCR'd.

## Interview questions you should be able to answer
1. **Why not a fixed-size splitter?** It ignores structure: it cuts bullets, mixes required with preferred, and blends employers. Section-aware chunks are about one thing, which makes both retrieval and citations precise.
2. **How did you choose the chunk size?** From the data: real resume entries are 300–600 chars, so 1200 keeps each entry whole while still splitting long JD sections. Overlap of 200 chars (about one bullet) covers facts on boundaries.
3. **What is overlap for, and what does it cost?** It keeps facts that sit on a boundary intact. The cost is duplicated tokens in storage and in the prompt if both neighbours are retrieved.
4. **Why store chunks in SQLite if you have a vector DB?** Source of truth vs. index. Rename/delete/list are relational operations, and the index can be rebuilt after a model or chunking change without re-uploading.
5. **How do you test chunking?** Pure functions with small fictional fixtures. The tests cover header synonyms, per-doc-type meaning, entry metadata, max size, overlap, no mid-bullet splits, and the hard-cut fallback.
6. **What breaks it?** Unusual headers, two-column PDFs, entry formats without dates. Next step: an LLM fallback that labels sections when the regex finds none.

## Further reading
- Pinecone — "Chunking Strategies for LLM Applications"
- Anthropic — "Introducing Contextual Retrieval" (prepending context to chunks; we'll use a light version in M4)
- PyMuPDF docs — `Page.get_text()` modes
- FastAPI docs — "Bigger Applications" (routers) and "Testing" (TestClient)
