"""Run a golden set end to end against the real models and print a pass rate.

    python -m app.eval.run app/eval/golden.yaml            # committed sample set (make eval)
    python -m app.eval.run ../samples/golden.private.yaml  # private set on your own documents

Uses a throwaway SQLite registry and its own Chroma collection, so it never touches your app data.
Needs ANTHROPIC_API_KEY, OPENAI_API_KEY and Chroma running. Costs roughly $0.10-0.30 per run.
"""

import argparse
import json
import logging
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.chat.service import retrieve_for_question, stream_answer
from app.config import get_settings
from app.eval.grading import Case, EvalSet, grade_case, grade_fit, load_eval_set
from app.fit.service import fit_for_all
from app.ingest.service import ingest_document
from app.main import build_services
from app.observability import metrics
from app.services import Services


class CaseResult(BaseModel):
    id: str
    question: str
    passed: bool
    failures: list[str]
    routed: list[str]
    cited: list[str]
    answer: str
    latency_ms: int
    cost_usd: float


class FitResult(BaseModel):
    job: str
    score: int
    passed: bool
    failures: list[str]


def ingest_all(svc: Services, eval_set: EvalSet, base: Path) -> dict[str, str]:
    """Resume first, then jobs in file order, so job keys map to Job #1, #2, ... predictably."""
    keymap: dict[str, str] = {}
    ordered = sorted(eval_set.documents.items(), key=lambda kv: kv[1].type != "resume")
    for key, spec in ordered:
        path = (base / spec.path).resolve()
        doc = ingest_document(svc, path.name, path.read_bytes(), spec.type)
        keymap[key] = doc.doc_id
        print(f"  ingested {key:8} -> {doc.label}  ({doc.chunk_count} chunks"
              f"{', WARNINGS: ' + str(len(doc.warnings)) if doc.warnings else ''})")
    return keymap


def run_case(svc: Services, case: Case, key_of: dict[str, str]) -> CaseResult:
    cost_before = metrics.snapshot()["llm"]["estimated_cost_usd"]
    started = time.perf_counter()
    retrieval = retrieve_for_question(svc, case.question)
    parts: list[str] = []
    done: dict[str, Any] = {}
    for event, data in stream_answer(svc, case.question, retrieval):
        if event == "token":
            parts.append(data["text"])
        elif event in ("done", "error"):
            done = {"event": event, **data}
    answer = "".join(parts) if done.get("event") == "done" else f"[error] {done.get('detail')}"

    by_n = {s.n: s.chunk.doc_id for s in retrieval.sources}
    routed = {key_of.get(d, d) for d in retrieval.route.doc_ids}
    cited = {key_of.get(by_n[n], "?") for n in done.get("citations", []) if n in by_n}
    failures = grade_case(case, answer, routed, cited)
    return CaseResult(
        id=case.id, question=case.question, passed=not failures, failures=failures,
        routed=sorted(routed), cited=sorted(cited), answer=answer,
        latency_ms=round((time.perf_counter() - started) * 1000),
        cost_usd=round(metrics.snapshot()["llm"]["estimated_cost_usd"] - cost_before, 4),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a RoleLens golden set.")
    parser.add_argument("golden", type=Path)
    parser.add_argument("--only", help="comma-separated case ids to run")
    parser.add_argument("--min-pass", type=float, default=0.0, help="exit 1 if the pass rate is below this (0-1)")
    args = parser.parse_args(argv)
    logging.getLogger().setLevel(logging.WARNING)  # keep the report readable; warnings still print as JSON

    eval_set = load_eval_set(args.golden)
    base = args.golden.parent
    with tempfile.TemporaryDirectory() as tmp:
        settings = get_settings().model_copy(update={
            "registry_db_path": Path(tmp) / "eval.sqlite3",
            "chroma_collection": f"rolelens_eval_{eval_set.name}",
        })
        svc = build_services(settings)
        svc.store.reset()

        print(f"\nRoleLens eval: {eval_set.name} ({len(eval_set.cases)} cases, {len(eval_set.fit_checks)} fit checks)")
        keymap = ingest_all(svc, eval_set, base)
        key_of = {doc_id: key for key, doc_id in keymap.items()}

        cases = [c for c in eval_set.cases if not args.only or c.id in args.only.split(",")]
        results: list[CaseResult] = []
        print()
        for case in cases:
            r = run_case(svc, case, key_of)
            results.append(r)
            mark = "PASS" if r.passed else "FAIL"
            print(f"  {mark}  {r.id:24} {r.latency_ms / 1000:5.1f}s  ${r.cost_usd:.4f}  route={','.join(r.routed)}")
            for f in r.failures:
                print(f"        - {f}")

        fits: list[FitResult] = []
        if eval_set.fit_checks and not args.only:
            print("\n  fit checks")
            reports = {key_of[f.job_id]: f for f in fit_for_all(svc)}
            for check in eval_set.fit_checks:
                score = reports[check.job].score
                failures = grade_fit(check, score)
                fits.append(FitResult(job=check.job, score=score, passed=not failures, failures=failures))
                print(f"  {'PASS' if not failures else 'FAIL'}  {check.job:8} score={score:3}  {'; '.join(failures)}")
        svc.store.reset()  # leave no eval vectors behind

    passed = sum(r.passed for r in results)
    fit_passed = sum(f.passed for f in fits)
    total_cost = metrics.snapshot()["llm"]["estimated_cost_usd"]
    rate = passed / len(results) if results else 0.0
    print(f"\n  Q&A cases: {passed}/{len(results)} passed ({rate:.0%})"
          + (f"   fit checks: {fit_passed}/{len(fits)}" if fits else "")
          + f"   total cost ${total_cost:.3f}\n")

    out_dir = base / "results"
    out_dir.mkdir(exist_ok=True)
    report = {
        "set": eval_set.name, "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "chat_model": settings.chat_model, "fast_model": settings.fast_model,
        "cases_passed": passed, "cases_total": len(results), "pass_rate": round(rate, 3),
        "fit_passed": fit_passed, "fit_total": len(fits), "total_cost_usd": round(total_cost, 4),
        "cases": [r.model_dump() for r in results], "fit": [f.model_dump() for f in fits],
    }
    (out_dir / f"{eval_set.name}-latest.json").write_text(json.dumps(report, indent=2))
    return 0 if rate >= args.min_pass else 1


if __name__ == "__main__":
    sys.exit(main())
