"""Fit dashboard use case.

The expensive part (LLM skill matching) is cached per (job, resume) pair in SQLite. The report
itself is recomputed from the cache on every request, so changing the scoring rules never needs
a new LLM call. A new resume has a new doc_id, so its matches are computed fresh.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from app.fit.matching import match_skills
from app.fit.resume_facts import experience_years, fact_skills
from app.fit.scoring import combine, summarize
from app.ingest.extraction import parse_extraction
from app.ingest.registry import DocumentNotFound
from app.llm.prompts import MATCH_PROMPT_VERSION
from app.models import DocumentSummary, FitReport, JobExtraction, ResumeExtraction, SkillMatchItem
from app.services import Services

logger = logging.getLogger(__name__)


class NoResume(Exception):
    pass


class NotAJob(Exception):
    pass


def _resume(svc: Services) -> tuple[DocumentSummary, ResumeExtraction]:
    ids = svc.registry.resume_ids()
    if not ids:
        raise NoResume("Upload your resume to see fit scores.")
    doc_type, data = svc.registry.get_extraction(ids[0])
    extraction = parse_extraction(doc_type, data or {"candidate_name": None, "headline": None,
                                                     "total_years_experience": None, "skills": []})
    assert isinstance(extraction, ResumeExtraction)
    # Deterministic facts from the text: years from dated roles (extraction only as fallback),
    # plus education and experience as extra evidence items for the matcher.
    text = svc.registry.get_raw_text(ids[0])
    years = experience_years(text, date.today())
    years = years if years is not None else extraction.total_years_experience
    extraction = extraction.model_copy(update={
        "total_years_experience": years,
        "skills": extraction.skills + fact_skills(text, years),
    })
    return svc.registry.get_summary(ids[0]), extraction


def _job(svc: Services, job_id: str) -> tuple[DocumentSummary, JobExtraction]:
    summary = svc.registry.get_summary(job_id)
    if summary.doc_type != "job":
        raise NotAJob(job_id)
    doc_type, data = svc.registry.get_extraction(job_id)
    extraction = parse_extraction(doc_type, data or {"title": None, "company": None, "seniority": "unspecified",
                                                     "min_years_experience": None, "skills": []})
    assert isinstance(extraction, JobExtraction)
    return summary, extraction


def _matches(svc: Services, job_id: str, job: JobExtraction, resume_id: str,
             resume: ResumeExtraction) -> dict[int, SkillMatchItem]:
    cached = svc.registry.get_fit_matches(job_id, resume_id)
    if cached is not None and cached.get("version") == MATCH_PROMPT_VERSION:
        return {int(k): SkillMatchItem.model_validate(v) for k, v in cached["items"].items()}
    matches, usage = match_skills(svc.llm, svc.settings.fast_model, job.skills, resume.skills)
    svc.registry.set_fit_matches(job_id, resume_id, {
        "version": MATCH_PROMPT_VERSION,
        "items": {str(k): v.model_dump() for k, v in matches.items()},
    })
    logger.info("fit matched", extra={"job_id": job_id, "cost_usd": usage.cost_usd if usage else 0.0})
    return matches


def fit_for_job(svc: Services, job_id: str) -> FitReport:
    resume_doc, resume = _resume(svc)
    job_doc, job = _job(svc, job_id)
    matches = _matches(svc, job_id, job, resume_doc.doc_id, resume)
    fits = combine(job.skills, resume, matches)
    return FitReport(
        job_id=job_id, job_label=job_doc.label, job_number=job_doc.job_number,
        title=job.title, company=job.company, seniority=job.seniority,
        **summarize(job, resume, fits),  # type: ignore[arg-type]
    )


def fit_for_all(svc: Services) -> list[FitReport]:
    """All jobs, in job-number order. Cache misses run in parallel (one Haiku call each)."""
    _resume(svc)  # fail fast with a clear message if there is no resume
    job_ids = [d.doc_id for d in svc.registry.list_summaries() if d.doc_type == "job"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda jid: fit_for_job(svc, jid), job_ids))


__all__ = ["DocumentNotFound", "NoResume", "NotAJob", "fit_for_all", "fit_for_job"]
