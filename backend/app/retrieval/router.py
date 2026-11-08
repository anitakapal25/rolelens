"""Query routing: decide which documents a question is about BEFORE searching.

Order:
1. keyword_route(): deterministic rules for explicit references ("Job #2", "the Platinus role",
   "my resume", "compare these roles"). Free, instant, predictable.
2. LLM route (Haiku, structured output) when the rules are unsure.
3. Fallback: resume + all jobs if the LLM call fails. Over-including is safer than missing a doc.

The resume is included whenever a job is, because nearly every job question is really
"... compared to me".
"""

import logging
import re

from pydantic import BaseModel

from app.ingest.extraction import short_company
from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_route_prompt
from app.models import RouteDecision, RouteResult, RouteScope

logger = logging.getLogger(__name__)


class DocRef(BaseModel):
    """What the router knows about each document."""

    doc_id: str
    doc_type: str
    label: str
    job_number: int | None = None
    title: str | None = None
    company: str | None = None


ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4,
            "fifth": 5, "5th": 5}
JOB_NUMBER = re.compile(r"\b(?:job|role|jd|position)\s*(?:#|no\.?|number)?\s*(\d{1,2})\b", re.IGNORECASE)
JOB_ORDINAL = re.compile(rf"\b({'|'.join(ORDINALS)})\s+(?:job|role|jd|position)\b", re.IGNORECASE)
COMPARATIVE = re.compile(
    r"\b(compare|comparison|versus|vs\.?|which (?:job|role|position|one)s?|best fit|fits? me best|"
    r"rank|across|all (?:the |these |my )?(?:jobs|roles|positions)|these (?:jobs|roles|positions)|"
    r"each (?:job|role)|every (?:job|role))\b",
    re.IGNORECASE,
)
RESUME_ONLY = re.compile(r"\b(my (?:resume|cv)|in my resume|on my resume)\b", re.IGNORECASE)
JOB_WORDS = re.compile(r"\b(jobs?|roles?|positions?|jds?|requirements?|missing|gaps?|fit|match)\b", re.IGNORECASE)
GENERIC_COMPANY_WORDS = {"solutions", "systems", "labs", "group", "global", "services", "software", "the"}


def _mentioned_companies(question: str, jobs: list[DocRef]) -> list[DocRef]:
    hits = []
    for job in jobs:
        if not job.company:
            continue
        name = short_company(job.company)
        # Match the full short name, or its first distinctive word ("Platinus", "HCLTech").
        candidates = {name} | {w for w in name.split()[:1] if len(w) >= 4 and w.lower() not in GENERIC_COMPANY_WORDS}
        if any(re.search(rf"\b{re.escape(c)}\b", question, re.IGNORECASE) for c in candidates):
            hits.append(job)
    return hits


def keyword_route(question: str, docs: list[DocRef]) -> RouteResult | None:
    """Deterministic routing for explicit references. Returns None when unsure."""
    resume_ids = [d.doc_id for d in docs if d.doc_type == "resume"]
    jobs = sorted((d for d in docs if d.doc_type == "job"), key=lambda d: d.job_number or 0)
    by_number = {j.job_number: j for j in jobs}

    numbers = {int(m) for m in JOB_NUMBER.findall(question)}
    numbers |= {ORDINALS[m.lower()] for m in JOB_ORDINAL.findall(question)}
    named = [by_number[n] for n in sorted(numbers) if n in by_number]
    named += [j for j in _mentioned_companies(question, jobs) if j not in named]

    if named:
        ids = resume_ids + [j.doc_id for j in named]
        return RouteResult(doc_ids=ids, scope="specific_jobs", method="keyword",
                           reason="explicit job reference: " + ", ".join(j.label for j in named))
    if numbers:  # "Job #7" that doesn't exist: let the answer say so, with all docs in view.
        return RouteResult(doc_ids=resume_ids + [j.doc_id for j in jobs], scope="all_jobs", method="keyword",
                           reason=f"unknown job number(s) {sorted(numbers)}")
    if COMPARATIVE.search(question):
        return RouteResult(doc_ids=resume_ids + [j.doc_id for j in jobs], scope="all_jobs", method="keyword",
                           reason="comparative question")
    if RESUME_ONLY.search(question) and not JOB_WORDS.search(question):
        return RouteResult(doc_ids=resume_ids, scope="resume_only", method="keyword",
                           reason="question about the resume only")
    return None


def apply_decision(decision: RouteDecision, docs: list[DocRef]) -> tuple[list[str], RouteScope]:
    resume_ids = [d.doc_id for d in docs if d.doc_type == "resume"]
    jobs = [d for d in docs if d.doc_type == "job"]
    if decision.scope == "resume_only":
        return resume_ids, "resume_only"
    if decision.scope == "specific_jobs":
        picked = [j.doc_id for j in jobs if j.job_number in set(decision.job_numbers)]
        if picked:
            return resume_ids + picked, "specific_jobs"
    return resume_ids + [j.doc_id for j in jobs], "all_jobs"


def route_question(question: str, docs: list[DocRef], llm: LLMClient, model: str) -> RouteResult:
    if not docs:
        return RouteResult(doc_ids=[], scope=None, method="empty", reason="no documents uploaded")

    by_rule = keyword_route(question, docs)
    if by_rule is not None:
        return by_rule

    if not any(d.doc_type == "job" for d in docs):  # only a resume: nothing to choose
        return RouteResult(doc_ids=[d.doc_id for d in docs], scope="resume_only", method="keyword",
                           reason="only a resume is uploaded")

    system, user = build_route_prompt(question, docs)
    try:
        decision, _ = llm.extract(model=model, system=system, user=user, schema=RouteDecision, max_tokens=1000)
    except LLMError as exc:
        logger.warning("routing LLM failed; using fallback", extra={"error": str(exc)})
        ids = [d.doc_id for d in docs]
        return RouteResult(doc_ids=ids, scope="all_jobs", method="fallback", reason="router unavailable")

    ids, scope = apply_decision(decision, docs)
    return RouteResult(doc_ids=ids, scope=scope, method="llm",
                       reason=f"llm: {decision.scope} {decision.job_numbers or ''}".strip())
