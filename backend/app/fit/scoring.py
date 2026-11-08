"""Deterministic fit scoring. Pure functions: no LLM, no I/O.

The LLM only decides match / partial / missing per job skill (fit/matching.py). Everything a user
sees as a number is computed here, so every point of the score can be explained:

    weight(skill)  = EMPHASIS[emphasis] x IMPORTANCE[importance]
                     core 3 / supporting 2 / minor 1;  required x1, preferred x0.5
    credit(status) = match 1.0 / partial 0.5 / missing 0
    experience     = one extra "required, supporting" item (weight 2) when both years are known
    score          = round(100 x sum(weight x credit) / sum(weight))
"""

from app.models import (
    Emphasis,
    ExperienceFit,
    FitCounts,
    Importance,
    JobExtraction,
    JobSkill,
    MatchStatus,
    ResumeExtraction,
    SkillFit,
    SkillMatchItem,
    Verdict,
)

EMPHASIS_WEIGHT: dict[Emphasis, float] = {"core": 3.0, "supporting": 2.0, "minor": 1.0}
IMPORTANCE_FACTOR: dict[Importance, float] = {"required": 1.0, "preferred": 0.5}
CREDIT: dict[MatchStatus, float] = {"match": 1.0, "partial": 0.5, "missing": 0.0}
EXPERIENCE_WEIGHT = 2.0

VERDICT_BANDS: list[tuple[int, Verdict]] = [(75, "strong"), (55, "good"), (35, "stretch"), (0, "weak")]
VERDICT_LABEL: dict[Verdict, str] = {
    "strong": "Strong fit",
    "good": "Good fit with gaps",
    "stretch": "Stretch",
    "weak": "Weak fit",
}


def skill_weight(importance: Importance, emphasis: Emphasis) -> float:
    return EMPHASIS_WEIGHT[emphasis] * IMPORTANCE_FACTOR[importance]


def experience_fit(required: float | None, candidate: float | None) -> ExperienceFit:
    met = None if required is None or candidate is None else candidate >= required
    return ExperienceFit(required_years=required, candidate_years=candidate, met=met)


def fit_score(skills: list[SkillFit], experience: ExperienceFit) -> int:
    total = sum(s.weight for s in skills)
    earned = sum(s.weight * CREDIT[s.status] for s in skills)
    if experience.met is not None:
        total += EXPERIENCE_WEIGHT
        earned += EXPERIENCE_WEIGHT if experience.met else 0.0
    return round(100 * earned / total) if total else 0


def verdict_for(score: int) -> Verdict:
    return next(v for floor, v in VERDICT_BANDS if score >= floor)


def rank_by_prominence(skills: list[SkillFit]) -> list[SkillFit]:
    """Highest weight first; required before preferred on ties; original order otherwise."""
    return sorted(skills, key=lambda s: (-s.weight, s.importance != "required"))


def count(skills: list[SkillFit]) -> FitCounts:
    def n(importance: Importance, status: MatchStatus | None = None) -> int:
        return sum(1 for s in skills if s.importance == importance and (status is None or s.status == status))

    return FitCounts(
        required_total=n("required"), required_matched=n("required", "match"),
        required_partial=n("required", "partial"),
        preferred_total=n("preferred"), preferred_matched=n("preferred", "match"),
        preferred_partial=n("preferred", "partial"),
    )


def verdict_text(verdict: Verdict, counts: FitCounts, missing: list[SkillFit], experience: ExperienceFit) -> str:
    parts = [f"{VERDICT_LABEL[verdict]}: you match {counts.required_matched} of {counts.required_total} required skills"]
    if counts.required_partial:
        parts[0] += f" ({counts.required_partial} partly)"
    # The headline gap should be actionable: prefer a required hard skill over soft skills.
    hard = [s for s in missing if s.category != "soft_skill"]
    gap = next((s for s in hard if s.importance == "required"), None) or (hard[0] if hard else None)
    if gap:
        parts.append(f"biggest gap: {gap.name}")
    if experience.met is False:
        parts.append(f"asks for {experience.required_years:g}+ years (you show {experience.candidate_years:g})")
    return "; ".join(parts) + "."


def combine(
    job_skills: list[JobSkill],
    resume: ResumeExtraction,
    matches: dict[int, SkillMatchItem],
) -> list[SkillFit]:
    """Join job skills with the match judgement and the resume's own verbatim evidence."""
    fits = []
    for i, skill in enumerate(job_skills):
        item = matches.get(i)
        status: MatchStatus = item.status if item else "missing"
        resume_hits = []
        for j in item.resume_skills if item else []:
            # Several skills often share one quote ("AI & retrieval: LLM-enabled applications, ..."): show it once.
            if 0 <= j < len(resume.skills) and resume.skills[j].evidence not in {r.evidence for r in resume_hits}:
                resume_hits.append(resume.skills[j])
        fits.append(SkillFit(
            name=skill.name, category=skill.category, importance=skill.importance, emphasis=skill.emphasis, status=status,
            weight=skill_weight(skill.importance, skill.emphasis), job_evidence=skill.evidence,
            resume_skills=[r.name for r in resume_hits], resume_evidence=[r.evidence for r in resume_hits],
            note=item.note if item else "Not assessed.",
        ))
    return fits


def summarize(job: JobExtraction, resume: ResumeExtraction, fits: list[SkillFit]) -> dict[str, object]:
    """Everything FitReport needs beyond identity fields."""
    experience = experience_fit(job.min_years_experience, resume.total_years_experience)
    score = fit_score(fits, experience)
    verdict = verdict_for(score)
    counts = count(fits)
    missing = rank_by_prominence([f for f in fits if f.status == "missing"])
    return {
        "score": score,
        "verdict": verdict,
        "verdict_text": verdict_text(verdict, counts, missing, experience),
        "experience": experience,
        "counts": counts,
        "matched": rank_by_prominence([f for f in fits if f.status == "match"]),
        "partial": rank_by_prominence([f for f in fits if f.status == "partial"]),
        "missing": missing,
    }
