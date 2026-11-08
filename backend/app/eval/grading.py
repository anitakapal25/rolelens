"""Eval set schema and deterministic graders. Pure: no network, no model calls.

Deterministic checks (substrings, routing sets, citation targets) are cheap, reproducible and
explainable. Their blind spot is paraphrase; an LLM judge is the listed next step.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Expect = Literal["answer", "not_in_docs", "off_topic"]

NOT_IN_DOCS_PHRASES = [
    "don't show", "doesn't show", "do not show", "does not show", "not shown",
    "don't mention", "doesn't mention", "do not mention", "does not mention", "not mentioned", "no mention",
    "don't say", "doesn't say", "does not say", "don't list", "doesn't list", "not listed", "isn't listed",
    "aren't listed", "no evidence", "nothing in your", "don't include", "doesn't include",
]
OFF_TOPIC_PHRASES = [
    "outside what rolelens", "outside the scope", "outside my scope", "can only help", "only help with",
    "not something rolelens", "isn't something rolelens", "something rolelens can't", "can't help with",
    "cannot help with", "isn't something i can help", "i'm limited to", "i am limited to", "limited to your resume",
]


class DocSpec(BaseModel):
    path: str
    type: Literal["resume", "job"]


class Case(BaseModel):
    id: str
    question: str
    expect: Expect = "answer"
    route: list[str] | None = None
    must_include: list[list[str]] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    must_cite: list[str] = Field(default_factory=list)


class FitCheck(BaseModel):
    job: str
    min_score: int | None = None
    max_score: int | None = None
    reason: str = ""


class EvalSet(BaseModel):
    name: str
    documents: dict[str, DocSpec]
    cases: list[Case]
    fit_checks: list[FitCheck] = Field(default_factory=list)


def load_eval_set(path: Path) -> EvalSet:
    return EvalSet.model_validate(yaml.safe_load(path.read_text()))


def _norm(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'").lower()


def grade_case(
    case: Case,
    answer: str,
    routed_keys: set[str],
    cited_keys: set[str],
) -> list[str]:
    """Return a list of failure reasons; empty means the case passed."""
    failures: list[str] = []
    text = _norm(answer)

    if case.route is not None and routed_keys != set(case.route):
        failures.append(f"route {sorted(routed_keys)} != expected {sorted(case.route)}")
    for group in case.must_include:
        if not any(_norm(alt) in text for alt in group):
            failures.append(f"missing one of {group}")
    for banned in case.must_not_include:
        if _norm(banned) in text:
            failures.append(f"contains banned text {banned!r}")
    missing_cites = set(case.must_cite) - cited_keys
    if missing_cites:
        failures.append(f"no citation into {sorted(missing_cites)}")
    if case.expect == "not_in_docs" and not any(p in text for p in NOT_IN_DOCS_PHRASES):
        failures.append("did not say the documents don't show it")
    if case.expect == "off_topic" and not any(p in text for p in OFF_TOPIC_PHRASES):
        failures.append("did not decline the off-topic question")
    return failures


def grade_fit(check: FitCheck, score: int) -> list[str]:
    failures = []
    if check.min_score is not None and score < check.min_score:
        failures.append(f"score {score} < min {check.min_score}")
    if check.max_score is not None and score > check.max_score:
        failures.append(f"score {score} > max {check.max_score}")
    return failures
