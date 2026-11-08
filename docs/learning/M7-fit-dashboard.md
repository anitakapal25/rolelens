# M7 — Fit dashboard

## What we built
| File | Purpose |
|---|---|
| `backend/app/fit/matching.py` | `match_skills()`: one Haiku call per (job, resume); `normalize_matches()` (pure) |
| `backend/app/fit/scoring.py` | Pure scoring: weights, `fit_score`, `verdict_for`, `rank_by_prominence`, `verdict_text`, `combine`, `summarize` |
| `backend/app/fit/resume_facts.py` | Pure: `experience_years()` from dated roles, `education_lines()`, `fact_skills()` |
| `backend/app/fit/service.py` | `fit_for_job`, `fit_for_all` (parallel on cache misses), versioned cache |
| `backend/app/api/fit.py` | `GET /fit` (all jobs), `GET /fit/{job_id}`; 409 when no resume |
| `backend/app/llm/prompts.py` | `MATCH_SYSTEM`, `build_match_prompt`, `MATCH_PROMPT_VERSION` |
| `backend/app/ingest/registry.py` | `fit_cache` table (FK cascade to both docs), `get_raw_text` |
| `frontend/src/components/FitDashboard.tsx` | Comparison bars, hero score + meter, stat tiles, Missing / Partial / Matched lists with evidence |
| `frontend/src/App.tsx` | Chat / Fit dashboard tabs (chat stays mounted so history survives) |
| Tests | 114 total. New: scoring (15+), resume facts (3), normalisation, prompt, API + cache invalidation (4) |

Result on your documents (one run, cached):
```
Job #2  Senior Forward Deployed Engineer, Platinus   82  Strong fit   6/10 required (+4 partly), 9.2 yrs vs 8+ met
Job #3  Forward Deployment Engineer                  67  Good fit     biggest gap: Django
Job #1  Forward Deployed Engineer, HCLTech           64  Good fit     8/18 required (+6 partly), biggest gap: Java
```
Cold `/fit` takes about 8 s (three Haiku calls in parallel); cached takes about 30 ms.

## Why this approach

### 1. The LLM judges, code counts
The tempting design is "ask the model: score this resume against this job, 0–100". It fails three ways:
- **Unexplainable:** why 72 and not 68? Nobody can say, including the model.
- **Unstable:** ask twice, get two numbers.
- **Unauditable:** you can't check it against anything.

So the work is split:
| Step | Who | Why |
|---|---|---|
| Skill lists (per document, at upload) | Haiku, structured output (M4) | Reading free text needs language understanding |
| Does the resume cover requirement J3? | Haiku, one call per job | Synonyms and judgment: "LLMs" ≈ "LLM-enabled applications", "FastAPI" satisfies "Python web framework" |
| Weights, score, verdict, ranking, years | **Plain Python** | Must be explainable, stable and testable |

Every number on screen comes from `scoring.py`, a file with no I/O and 15+ unit tests. The UI's "How is the score calculated?" box is the same formula in plain English.

### 2. The formula
```
weight  = {core: 3, supporting: 2, minor: 1}[emphasis] × {required: 1, preferred: 0.5}[importance]
credit  = {match: 1, partial: 0.5, missing: 0}[status]
score   = round(100 × Σ weight×credit / Σ weight)       (+ experience as one weight-2 item when both years are known)
verdict = ≥75 Strong · ≥55 Good fit with gaps · ≥35 Stretch · else Weak
```
Design reasoning:
- A missing **required core** skill costs 6× more than a missing **preferred minor** one (3 vs 0.5). That matches how recruiters read a JD.
- Partial = half credit: "AWS fundamentals" for "AWS/Azure/GCP" is neither nothing nor a full match.
- Missing skills are ranked by the same weight, so "ranked by prominence in the JD" falls out of the formula for free.

### 3. Making the model's answer safe to use
The matcher sees numbered lists and answers with **numbers**:
```
J1. Python (required, core) — "Strong experience in Python programming."
R7. FastAPI [framework] — "FastAPI, Flask, React, Vue 3"
→ {"job_skill": 1, "status": "match", "resume_skills": [1, 7], "note": "..."}
```
Free-text names ("Python 3.x") would have to be fuzzy-matched back to our lists; numbers map back exactly. `normalize_matches()` then enforces the rules in code:
- out-of-range numbers and duplicate items are dropped;
- a job skill the model skipped counts as **missing** ("Not assessed.");
- a "match" with no evidence numbers is **downgraded to partial**: a match must point at something;
- "missing" never carries evidence.

### 4. Problems the real data exposed (and fixes)
This milestone is a good example of **measuring before trusting**:
| What I saw on your documents | Cause | Fix |
|---|---|---|
| Experience check gone for every job | The re-run extraction returned `total_years_experience: null` | Compute years **in code** from dated roles (Sep 2017 – Present → 9.2); extraction is only a fallback |
| "Bachelor's degree" marked missing, despite your MCA | Extraction lists *skills*, not education | Add `Education: …` and `Professional experience: 9.2 years` as extra evidence items (`fact_skills`) |
| "Production deployments ← Python" as a match | Haiku at `low` effort was too generous | Effort `medium` + rule: "a language is never evidence for soft skills, years, deployments or domain" |
| Verdict said "biggest gap: Problem-solving" | Soft skills ranked like hard skills | "Biggest gap" skips `soft_skill` items |
| Same quote shown twice under one skill | Several resume skills share one line of evidence | De-duplicate quotes in `combine()` |
| Job #2 went 69 → 82 between two matching runs | LLM variance on borderline partial/match calls | **Cache per pair** (a given pair is stable) + document it honestly + measure in M8 |

### 5. Caching: cache the expensive judgment, not the result
`fit_cache` stores the **matches** (the LLM output), keyed by `(job_id, resume_id)`, not the final report. So:
- **Changing the weights or verdict bands** applies instantly, with no LLM calls.
- **A new resume** has a new `doc_id`, so it's a cache miss and gets fresh matches.
- **Deleting** either document cascades the cache rows away (foreign keys).
- **Changing the matching prompt:** each entry stores `MATCH_PROMPT_VERSION`, so bumping the version invalidates old entries. This is the step people forget, and stale caches after a prompt change are a classic LLM-app bug.

### 6. Choosing the visual forms (dataviz guidance)
| Need | Form | Rejected |
|---|---|---|
| One headline number per job | **Hero number** (48 px) + **meter** (teal fill on a lighter teal track) | Donut or gauge: harder to read, wastes space |
| Compare jobs | **Ranked horizontal bars**, best first, one hue, one baseline, value at the end, hover tooltip | Vertical bars with rotated labels; multicolour bars (colour would mean nothing) |
| Counts | **Stat tiles**: "6 / 10 required (+4 partly)" | A pie of matched/missing |
| Matched / partial / missing | **Icon + label + colour** (✓ teal, ◐ amber, ✕ rose as SVG) | Colour alone, which colour-blind users and print can't read |

The partial icon was first a Unicode "◐", which Inter doesn't include, so it rendered as a tiny broken glyph. Inline SVG icons look the same everywhere.

### 7. UX details
- The dashboard opens on the **best-fitting** job (the top bar), not Job #1.
- Each skill row expands to show: the model's note, the **job's verbatim quote**, and **your resume's verbatim quote(s)**. You can check every judgment yourself.
- States: no jobs, no resume (the API's 409 message), loading skeleton ("Matching each job's requirements against your resume…"), error.
- Chat stays mounted (hidden) when you switch tabs, so the conversation survives.

## Concepts / skills to learn
- **LLM-as-classifier vs. LLM-as-oracle:** small, checkable decisions (match/partial/missing with evidence) beat one big opaque judgment (a score).
- **Referencing by ID in prompts:** number your lists and ask for numbers back. It's robust to paraphrase and trivial to validate.
- **Deterministic post-processing:** never pass raw model output straight to the UI. Validate, repair and enforce invariants in code.
- **Cache keys and versioning:** key on every input that changes the output (job, resume, prompt version), and store the expensive part, not the derived part.
- **Thread pools for I/O-bound work:** three network-bound calls in parallel take about as long as the slowest one (~8 s), not the sum (~20 s). Each thread opens its own SQLite connection.
- **Accessible data visualisation:** `role="meter"` with `aria-valuenow`, tooltips on focus as well as hover, and labels that never depend on colour.

## How to verify it yourself
```bash
cd backend && ../.venv/bin/python -m pytest -q tests/test_fit_scoring.py tests/test_api_fit.py
curl -s localhost:8000/fit | python -m json.tool | less          # all three reports
curl -s localhost:8000/fit/<job_id> | python -m json.tool          # one job
open http://localhost:5173  → "Fit dashboard" tab
```
Try:
1. In `scoring.py`, change `IMPORTANCE_FACTOR["preferred"]` to `0.25` and reload the dashboard. Scores change instantly, with no LLM call. That's why the cache stores matches, not reports.
2. Expand every **Partial** item for Job #1. Do you agree with each one? Write down the ones you'd overrule; those are your eval cases for M8.
3. Bump `MATCH_PROMPT_VERSION` and reload: the first load is slow again (fresh matching), then fast.

## Known limitations (README material)
- **Matching variance:** borderline items flip between partial and match across runs (Job #2: 69 vs 82). Caching hides it per pair but doesn't remove it. Next steps: majority vote over 3 calls, or a fixed skill taxonomy.
- **Soft skills are noisy** both ways. Better: score them separately, or not at all.
- **Experience years count gaps between roles** (earliest start → latest end). Good enough here, but overlapping or part-time roles would overcount.
- **Weights are hand-set, not learned.** Defensible and explainable, but not validated against real hiring outcomes.

## Interview questions you should be able to answer
1. **How is the fit score computed, and why not ask the LLM for a score?** (Formula above.) LLM scores are unexplainable and unstable; small evidence-backed judgments plus deterministic arithmetic are auditable.
2. **How do you make the model's output reliable enough to compute on?** Structured output, reference by number, code-side normalisation (range checks, dedupe, "match needs evidence"), and a medium effort setting chosen by measuring.
3. **What did you find when you looked at real output?** The null years, the missing degree, generous matching and variance, each with its fix (table above).
4. **How does caching work and how does it invalidate?** Matches are keyed by (job, resume) with FK cascades, plus a prompt version, so scoring changes need no recompute.
5. **Why these chart types?** One number → hero + meter; compare a few roles → ranked bars on one baseline; status → icon + label, not colour alone.
6. **What would you change with more time?** Majority-vote matching, a skill taxonomy, separate soft-skill handling, and calibrating weights against real outcomes.

## Further reading
- Anthropic docs — "Increase output consistency"; structured outputs
- Eugene Yan — "Patterns for building LLM-based systems" (evals, guardrails, caching)
- The dataviz skill's `choosing-a-form.md` (hero number, meter, ranked bars)
