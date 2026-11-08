"""Structured extraction (one LLM call per document) and the auto-label derived from it."""

import re

from app.llm.client import LLMClient
from app.llm.prompts import build_extraction_prompt
from app.models import DocType, Extraction, JobExtraction, ResumeExtraction, Usage

COMPANY_SUFFIXES = re.compile(
    r"[,\s]+(pvt\.?\s*ltd\.?|private\s+limited|ltd\.?|limited|inc\.?|llc|gmbh|corp\.?|corporation|technologies)$",
    re.IGNORECASE,
)
MAX_TITLE_CHARS = 40


def extract_structured(llm: LLMClient, model: str, doc_type: DocType, text: str) -> tuple[Extraction, Usage]:
    system, user = build_extraction_prompt(doc_type, text)
    schema: type[ResumeExtraction] | type[JobExtraction] = (
        ResumeExtraction if doc_type == "resume" else JobExtraction
    )
    return llm.extract(model=model, system=system, user=user, schema=schema)


def parse_extraction(doc_type: DocType, data: dict[str, object]) -> Extraction:
    if doc_type == "resume":
        return ResumeExtraction.model_validate(data)
    return JobExtraction.model_validate(data)


def short_company(name: str) -> str:
    previous = None
    while previous != name:  # strip stacked suffixes: "Platinus Technologies Pvt. Ltd."
        previous = name
        name = COMPANY_SUFFIXES.sub("", name).strip()
    return name


def short_title(title: str) -> str:
    title = re.sub(r"\s*\([^)]*\)", "", title).strip()  # drop "(FDE)" style asides
    if len(title) <= MAX_TITLE_CHARS:
        return title
    cut = title[: MAX_TITLE_CHARS - 1]
    if " " in cut:  # end on a whole word
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,-–—") + "…"


def auto_label(doc_type: DocType, job_number: int | None, extraction: Extraction | None) -> str:
    """'Resume — Jane Doe' or 'Job #2 — Senior Backend Engineer, Acme'. Falls back to the bare prefix."""
    if doc_type == "resume":
        name = extraction.candidate_name if isinstance(extraction, ResumeExtraction) else None
        return f"Resume — {name}" if name else "Resume"
    prefix = f"Job #{job_number}"
    if not isinstance(extraction, JobExtraction):
        return prefix
    parts = [p for p in (
        short_title(extraction.title) if extraction.title else None,
        short_company(extraction.company) if extraction.company else None,
    ) if p]
    return f"{prefix} — {', '.join(parts)}" if parts else prefix
