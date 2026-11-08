# M2 — AI coding rules file

## What we built
| File | Purpose |
|---|---|
| `CLAUDE.md` | Rules every AI assistant session reads automatically: stack, structure, style, dependencies, tests, prompts, secrets |
| `docs/decisions.md` → **M2** entries + **AI workflow** section | Where the assistant helped, what you own, what it may not touch |

## Why this approach

### The problem it solves
An AI assistant starts each session with no memory of yesterday's choices. Without rules it will:
- suggest LangChain, SQLAlchemy or Next.js because they're common,
- put logic in route handlers because tutorials do,
- `pip install` a new package for every small feature,
- scatter prompt strings across files.

Each of these is reasonable alone. Together they produce a codebase nobody chose. A committed rules file makes the assistant's behaviour **repeatable** (same constraints every session, for every developer) and **reviewable** (the rules are in git, so changes to them are visible).

### Why `CLAUDE.md` (and not `.cursorrules` / a wiki page)
- Claude Code loads `CLAUDE.md` from the repo root on its own, with no copy-pasting into the chat.
- It's plain Markdown, so humans read it as onboarding and other tools can be pointed at it.
- It lives *in the repo*, so it changes with the code and shows up in review. A wiki page drifts.

### Why each rule is there
| Rule | What goes wrong without it |
|---|---|
| **Fixed stack, "do not suggest alternatives"** | The assistant spends tokens (and your attention) re-arguing settled choices. |
| **No logic in route handlers** | You can't unit-test logic without an HTTP server, and the eval runner can't reuse it. |
| **Ask before adding a dependency** | The single most valuable rule. Every package is attack surface, install time, version conflicts, and something you must explain in the interview. |
| **Type hints + Pydantic at boundaries** | LLM output is untyped JSON. Validating it into a model turns "the model returned garbage" into a clear error at a known place. |
| **No bare `except`** | `except: pass` hides the real failure, e.g. an expired API key looks like "no results". |
| **Tests for pure functions in `ingest/` and `retrieval/`** | Chunking and filtering fail *silently*: you just get worse answers. Only tests catch that. |
| **All prompts in `llm/prompts.py`** | Prompts are behaviour. One file means one place to review, diff and test them, and to check injection defences. |
| **Inject clients as arguments** | Lets tests pass a fake LLM, so tests are fast, free and don't depend on the network. |
| **Hand-written section** | Prompt assembly and retrieval scoring are where correctness lives. You must be able to defend every line in an interview. |

### Rejected alternatives
- **No rules file, just good prompts each time.** Not repeatable, and every new session starts from zero.
- **A very long rules file (style-guide sized).** Assistants follow short, specific rules better. Anything that a linter can check should be checked by a linter instead.
- **Letting the assistant write everything.** The brief says reviewers will notice LLM-written reasoning. Owning the core logic and the README reasoning is both honest and good interview prep.

## Concepts / skills to learn
- **Context engineering:** what the model sees decides what it does. A rules file is persistent context. The same idea later drives the RAG prompt: put the right text in front of the model.
- **Dependency injection** (the simple kind): pass things in instead of building them inside.
  ```python
  # Hard to test: builds its own client
  def route(question: str) -> list[str]:
      client = Anthropic()
      ...

  # Easy to test: the caller supplies the client (a fake in tests)
  def route(question: str, llm: LLMClient) -> list[str]:
      ...
  ```
- **Boundary validation:** trust nothing that crosses a boundary (HTTP, LLM output, files). Validate once, at the edge, into a typed model. Inner code can then assume clean data.
- **Untrusted input in prompts:** documents can contain instructions ("ignore previous instructions…"). The rule is written down now, and implemented in M5 and M8.

## How to verify it yourself
```bash
cd ~/Documents/rolelens
cat CLAUDE.md
# In a new Claude Code session, ask: "add a function to call the LLM with LangChain"
# → it should refuse or ask, citing the stack rule.
# Ask: "install requests to fetch job URLs"
# → it should ask first and point out that scraping is out of scope.
```
Try these and write what happened in the **AI workflow → Log** of `docs/decisions.md`. Real observations are exactly what that section is for.

## Interview questions you should be able to answer
1. **How do you make AI-assisted development repeatable?** A committed rules file (stack, structure, dependency policy, test policy) plus a decisions log. Every session starts from the same constraints, and changes to them are reviewed like code.
2. **What do you not let the AI write, and why?** Prompt assembly, retrieval scoring and the reasoning in the docs. That's where correctness lives, and I need to explain and own it.
3. **Why ask before adding dependencies?** Supply-chain risk, image size, version conflicts, and every package is something to maintain and explain. The stdlib or an existing dependency is often enough.
4. **Why centralise prompts?** They're behaviour. Having them in one file makes them reviewable, diffable and testable, and keeps injection defences consistent.
5. **How do you test code that calls an LLM?** Inject the client and pass a fake that returns canned responses. Test the logic around the model, not the model itself. Model quality is the job of the eval set (M8).

## Further reading
- Claude Code docs — "Manage Claude's memory" (how `CLAUDE.md` is loaded)
- OWASP Top 10 for LLM Applications — LLM01 Prompt Injection
