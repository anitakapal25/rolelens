# M6 — Frontend: upload panel & streaming chat

## What we built
| File | Purpose |
|---|---|
| `frontend/package.json` | Pinned exact versions: React 19.3, Vite 8.3, TypeScript 7.0, Tailwind 4.3, react-markdown 10.1 |
| `frontend/vite.config.ts` | React + Tailwind plugins; `envDir: ".."` reads `VITE_*` from the repo-root `.env` |
| `frontend/src/index.css` | Design tokens in `@theme`: teal accent, stone neutrals, Inter, shimmer animation; answer typography |
| `src/lib/types.ts` | TypeScript mirror of the backend Pydantic models |
| `src/lib/sse.ts` | `createSSEParser()`: incremental Server-Sent Events parser |
| `src/lib/api.ts` | `listDocuments`, `uploadDocument`, `renameDocument`, `deleteDocument`, `streamChat`, `ApiError` |
| `src/lib/text.ts` | Pure helpers: `linkCitations`, `citationNumber`, `suggestedQuestions`, `displayLabel` |
| `src/components/UploadPanel.tsx` | Resume slot + job list, sequential upload queue, pending/error rows with elapsed timer |
| `src/components/DocumentCard.tsx` | Badge, click-to-rename, delete, detected-section chips |
| `src/components/Dropzone.tsx` | Drag-and-drop or click-to-pick (PDF/DOCX/TXT) |
| `src/components/Chat.tsx` | Turns, suggested-question chips, input (Enter / Shift+Enter), SSE event handling |
| `src/components/Answer.tsx` | Markdown answer, inline citation pills, source card, cited-sources row, latency + cost |
| `src/components/SourceCard.tsx`, `Skeleton.tsx` | Expanded source excerpt; shimmer placeholders |
| Backend | `registry.reserve_job_number()`: atomic counter (race fix) + 2 tests → 87 backend tests |

Verified by a scripted walkthrough in headless Chrome (Playwright run from a scratch folder, not a project dependency): empty state → drop resume + 3 JDs → queue → cards with sections → suggested question → skeleton → streamed answer → pill opens source. No console errors.

## Why this approach

### 1. Keep the frontend boring on purpose
Two panels (documents, chat) and one list of messages. So:
- **No state library** (Redux, Zustand): `App` owns `documents` and passes a `refresh()` down. After any upload, rename or delete we simply re-fetch `/documents`. The server is the source of truth, so there's no client cache to keep in sync.
- **No router, no UI kit:** nothing to route, and a kit would bring its own look and a lot of weight.
- **`lib/` vs `components/`** (CLAUDE.md rule): no JSX in `lib/`. `lib/text.ts` and `lib/sse.ts` are pure functions, easy to reason about and easy to test later.

### 2. Streaming: why not `EventSource`?
The browser's `EventSource` only does **GET** with no body. Our `/chat` is a **POST** with a JSON question. So we use `fetch`, read `res.body` as a stream, and parse SSE ourselves:
```ts
const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
for (;;) {
  const { value, done } = await reader.read();
  if (done) break;
  feed(value);            // createSSEParser: buffers until "\n\n", then emits {event, data}
}
```
**Buffering matters.** Network chunks don't line up with events: one read can hold half an event, or three. The parser keeps a buffer and only emits complete blocks, which is the classic bug in hand-rolled SSE clients.

### 3. The chat state machine
Each turn moves through `retrieving → streaming → done | error`:
| SSE event | UI change |
|---|---|
| (request sent) | user bubble + "Finding relevant parts of your documents…" skeleton |
| `route` | stores which docs were searched |
| `sources` | status `streaming`; "Searched 4 documents · 18 excerpts"; pills now resolvable |
| `token` | appended to the answer; blinking caret |
| `done` | cited-sources row, latency, cost |
| `error` / stream ends early | red message ("The answer was interrupted. Try again.") |

Updates use the functional form `setTurns(list => …)`. Tokens arrive faster than React re-renders, and the functional form always applies each update to the latest state, so tokens are never lost.

### 4. Citations: from `[3]` to a clickable pill
1. `linkCitations()` rewrites `[3]` to `[3](#cite-3)`, a normal markdown link.
2. react-markdown renders it; our custom `a` component sees `href="#cite-3"` and renders a **pill button** instead.
3. Clicking a pill shows a `SourceCard` (document label, section, entry and the exact chunk text) and scrolls it into view. All pills with the same number highlight together.

Why this way: react-markdown stays in its **safe default mode** (no raw HTML, so a malicious document can't inject `<script>` through an answer), and no extra plugin is needed. A pill whose number isn't in `sources` renders as plain text, so a made-up citation never becomes a broken button.

### 5. Uploads: a queue and honest progress
- **Sequential queue:** `queue.current = queue.current.then(() => upload(file))`. Every file, even across separate drops, waits its turn. This avoids hammering the LLM and embedding APIs (rate limits) and keeps job numbers in drop order.
- **Honest progress:** the server step takes 5–25 s and has no progress events, so a fake percentage would be lying. The UI says what is happening ("Reading, extracting skills and indexing… 12s") with a shimmering bar and an elapsed counter.
- **Errors stay on screen:** the API's message (e.g. "Unsupported file type '.png'…", "PDF has 14 pages; the limit is 10.") shows in a red row with *Dismiss*.

### 6. The backend race the queue exposed
Building the queue raised the question: *what if two job uploads do run in parallel* (two tabs, or a future change)? `next_job_number()` read `MAX(job_number)+1` at the **start** of a 5–20 s upload, and the row was inserted at the **end**. Two parallel uploads would both read 1 and both become "Job #2". Fix:
```sql
UPDATE counters SET value = value + 1 WHERE name = 'job' RETURNING value
```
That is one statement, so SQLite applies it atomically, and the counter lives in a table, so it survives restarts and numbers are never reused. A test fires 40 reservations from 8 threads and checks the result is exactly 1..40. Interview lesson: **check-then-act across a slow operation is a race**; make the check-and-act a single atomic step.

### 7. Design decisions that cost nothing
- **One accent, one neutral, one font**, defined as tokens in `@theme`: `accent-50…800` (teal), Tailwind's `stone` scale, Inter. Every colour in the UI comes from these, which is why it looks consistent.
- **Type scale:** 11 px meta, 13 px source text, 15 px body, 18 px headings, and nothing else.
- **Every async state is designed:** loading (shimmer cards), empty ("Start by adding your documents"), waiting (skeleton lines, not a spinner), streaming (caret), error (red, with the reason), done (sources + cost).
- **Labels:** the badge says "JOB 2", so the card title drops the "Job #2 —" prefix (`displayLabel`) and shows the full label on hover.
- **Suggested questions** use a company from your actual job labels ("What should I prepare for the HCLTech interview?").

## Concepts / skills to learn
- **Controlled inputs:** `value={draft}` + `onChange` keeps React state as the single source of truth for the textarea.
- **`useRef` for things that shouldn't re-render:** the upload queue promise and DOM nodes (scroll targets).
- **`useEffect` cleanup:** the elapsed-time interval is cleared when the upload finishes or the row unmounts. Otherwise timers leak.
- **Accessibility basics:** buttons are `<button>`s, pills have `aria-label="Show source 3"` and `aria-pressed`, upload rows use `aria-live="polite"`, and errors use `role="alert"`.
- **Vite env vars:** only `VITE_`-prefixed variables reach the browser bundle. Your API keys in the same `.env` are never exposed.
- **TypeScript strictness:** `strict`, `noUncheckedIndexedAccess`, `verbatimModuleSyntax`. Array indexing returns `T | undefined`, which forces handling of missing items.

## How to verify it yourself
```bash
docker compose up -d chroma
cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000     # terminal 1
cd frontend && npm install && npm run dev                                  # terminal 2
open http://localhost:5173
```
Try:
1. Drop all three job files at once and watch them queue.
2. Click a job title, rename it to "Platinus part-time", and ask "Is the Platinus role a fit?"
3. Click a citation pill and check the claim against the excerpt. Can you find an answer where a pill doesn't support its sentence?
4. Stop the backend and reload: you get the red "Can't reach the RoleLens API" banner with *Retry*.
5. `npm run build`: the strict type check plus the production bundle (~110 kB gzipped).

## Known limitations
- **No frontend unit tests.** The SSE parser and text helpers are pure and easy to test, but adding a test runner needs a new dependency. Listed under "standards skipped".
- **Chat history is lost on reload** (no conversation memory by design; see What's next).
- **No cancel button** while an answer streams.
- **Desktop-first layout:** on narrow screens the panels stack, but the chat isn't height-optimised for mobile.

## Interview questions you should be able to answer
1. **How does the token streaming work end to end?** FastAPI yields SSE blocks → browser `fetch` stream → TextDecoder → buffered SSE parser → typed events → functional `setState` appends tokens.
2. **Why not EventSource / WebSockets?** EventSource can't POST a body; WebSockets are two-way and overkill for one-way token streams.
3. **How are citations made interactive safely?** Rewrite `[n]` to an anchor, render markdown with raw HTML disabled, and swap anchors for buttons only when `n` exists in the sources sent before the answer.
4. **Tell me about a bug you found.** The job-number race: check-then-act across a slow upload, reproduced with a concurrent test, fixed with an atomic `UPDATE … RETURNING`.
5. **Why no Redux or React Query?** One owner of documents, re-fetched after each mutation, with the server as source of truth. The complexity isn't there to manage.
6. **How do you show progress for a step without progress events?** Show the steps and the elapsed time, never a fake percentage.

## Further reading
- MDN — "Using readable streams", "Server-sent events"
- react-markdown README — `components` prop and security
- Tailwind CSS v4 — "Theme variables" (`@theme`)
- React docs — "Queueing a series of state updates"
