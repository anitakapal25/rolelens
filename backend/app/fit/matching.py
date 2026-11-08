"""One Haiku call per (job, resume) pair: match / partial / missing for each job skill.

The model refers to skills by number, never by free text, so its answer maps back to our lists
exactly. normalize_matches() repairs anything out of range or missing.
"""

from app.llm.client import LLMClient
from app.llm.prompts import build_match_prompt
from app.models import JobSkill, ResumeSkill, SkillMatchItem, SkillMatchResult, Usage


def normalize_matches(result: SkillMatchResult, n_job: int, n_resume: int) -> dict[int, SkillMatchItem]:
    """Pure: 1-based model numbers -> 0-based indexes; drop out-of-range and duplicate items.

    Job skills the model skipped are simply absent; scoring treats them as missing ("Not assessed").
    """
    out: dict[int, SkillMatchItem] = {}
    for item in result.items:
        j = item.job_skill - 1
        if not 0 <= j < n_job or j in out:
            continue
        resume_ids = sorted({r - 1 for r in item.resume_skills if 0 < r <= n_resume})
        status = item.status
        if status != "missing" and not resume_ids:
            status = "partial" if status == "match" else status  # a match must point at evidence
        if status == "missing":
            resume_ids = []
        out[j] = SkillMatchItem(job_skill=j, status=status, resume_skills=resume_ids, note=item.note.strip())
    return out


def match_skills(
    llm: LLMClient, model: str, job_skills: list[JobSkill], resume_skills: list[ResumeSkill]
) -> tuple[dict[int, SkillMatchItem], Usage | None]:
    if not job_skills:
        return {}, None
    system, user = build_match_prompt(job_skills, resume_skills)
    # medium effort: at low, the model accepted weak evidence (e.g. "Python" for "production deployments").
    result, usage = llm.extract(model=model, system=system, user=user, schema=SkillMatchResult, effort="medium")
    return normalize_matches(result, len(job_skills), len(resume_skills)), usage
