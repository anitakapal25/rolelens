"""Facts read straight from the resume text, in code, so they don't depend on an LLM.

- experience_years(): span of the dated roles in the Experience section (earliest start to the
  latest end, "Present" = today). Gaps between roles are counted, so this is an upper bound.
- fact_skills(): education lines and total experience as extra "resume skills", so the matcher
  can satisfy requirements like "Bachelor's degree" or "5+ years of software engineering".
"""

import re
from datetime import date

from app.ingest.chunking import DATE_RANGE, detect_sections
from app.models import ResumeSkill

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
POINT = re.compile(r"(?:(?P<mon>[a-z]{3})[a-z]*\.?\s+)?(?P<year>\d{4})", re.IGNORECASE)
PRESENT = re.compile(r"present|current|now", re.IGNORECASE)


def _point(text: str, default_month: int) -> float | None:
    m = POINT.search(text)
    if not m:
        return None
    month = MONTHS.get((m.group("mon") or "").lower()[:3], default_month)
    return int(m.group("year")) + (month - 1) / 12


def experience_years(resume_text: str, today: date) -> float | None:
    experience = "\n".join(s.text for s in detect_sections(resume_text, "resume") if s.name == "experience")
    starts, ends = [], []
    now = today.year + (today.month - 1) / 12
    for match in DATE_RANGE.finditer(experience):
        start_text, _, end_text = re.split(r"\s*(-|–|—|to)\s*", match.group(0), maxsplit=1)
        start = _point(start_text, default_month=1)
        end = now if PRESENT.search(end_text) else _point(end_text, default_month=12)
        if start is not None and end is not None and end >= start:
            starts.append(start)
            ends.append(end)
    if not starts:
        return None
    return round(max(ends) - min(starts), 1)


def education_lines(resume_text: str) -> list[str]:
    edu = next((s.text for s in detect_sections(resume_text, "resume") if s.name == "education"), "")
    return [line.strip() for line in edu.split("\n") if line.strip() and not DATE_RANGE.fullmatch(line.strip())]


def fact_skills(resume_text: str, years: float | None) -> list[ResumeSkill]:
    facts = [ResumeSkill(name="Education", category="other", years=None, evidence=line)
             for line in education_lines(resume_text)]
    if years is not None:
        facts.append(ResumeSkill(name="Professional experience", category="other", years=years,
                                 evidence=f"{years:g} years across dated roles in the Experience section"))
    return facts
