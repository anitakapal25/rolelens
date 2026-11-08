"""Pydantic models shared across layers (HTTP bodies, registry records, chunks)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["resume", "job"]


class Chunk(BaseModel):
    """One retrievable piece of a document, with the metadata needed to filter and cite it."""

    chunk_id: str
    doc_id: str
    doc_type: DocType
    doc_label: str
    section: str
    index: int
    text: str
    company: str | None = None
    role: str | None = None
    entry: str | None = None


class SectionSummary(BaseModel):
    name: str
    chunk_count: int


class DocumentSummary(BaseModel):
    doc_id: str
    doc_type: DocType
    label: str
    filename: str
    job_number: int | None = None
    page_count: int
    char_count: int
    chunk_count: int
    sections: list[SectionSummary]
    created_at: datetime


class RenameRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)


class ErrorResponse(BaseModel):
    detail: str


class Usage(BaseModel):
    """Token usage and estimated cost of one model call."""

    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


# ---------- structured extraction (LLM output schemas) ----------
# Kept simple on purpose: these become JSON schemas for Claude structured outputs.

SkillCategory = Literal["language", "framework", "ai_ml", "data", "cloud_devops", "practice", "domain", "soft_skill", "other"]


class ResumeSkill(BaseModel):
    name: str = Field(description="Canonical short skill name, e.g. 'Python', 'FastAPI', 'RAG', 'AWS'.")
    category: SkillCategory
    years: float | None = Field(description="Years of hands-on use if it can be inferred from dated roles, else null.")
    evidence: str = Field(description="Short verbatim quote from the resume that shows this skill.")


class ResumeExtraction(BaseModel):
    candidate_name: str | None
    headline: str | None = Field(description="Current title or one-line positioning statement.")
    total_years_experience: float | None
    skills: list[ResumeSkill]


Importance = Literal["required", "preferred"]
Emphasis = Literal["core", "supporting", "minor"]
Seniority = Literal["junior", "mid", "senior", "staff_or_principal", "lead_or_manager", "unspecified"]


class JobSkill(BaseModel):
    name: str = Field(description="Canonical short skill name, e.g. 'Python', 'LangChain', 'Azure'.")
    category: SkillCategory
    importance: Importance
    emphasis: Emphasis = Field(description="core = central to the role or repeated; supporting = clearly asked for; minor = mentioned in passing.")
    min_years: float | None
    evidence: str = Field(description="Short verbatim quote from the job description.")


class JobExtraction(BaseModel):
    title: str | None
    company: str | None
    seniority: Seniority
    min_years_experience: float | None
    skills: list[JobSkill]


Extraction = ResumeExtraction | JobExtraction


# ---------- chat: routing, retrieval, answers ----------

RouteScope = Literal["resume_only", "specific_jobs", "all_jobs"]
RouteMethod = Literal["keyword", "llm", "fallback", "empty"]


class RouteDecision(BaseModel):
    """Structured output of the routing LLM call."""

    scope: RouteScope = Field(description="resume_only: only about the candidate. specific_jobs: about one or more named jobs. all_jobs: comparing or choosing across jobs, or about jobs in general.")
    job_numbers: list[int] = Field(description="Job numbers the question is about when scope is specific_jobs; otherwise empty.")


class RouteResult(BaseModel):
    doc_ids: list[str]
    scope: RouteScope | None
    method: RouteMethod
    reason: str


class RetrievedChunk(BaseModel):
    """A chunk selected for the prompt, numbered as it will be cited: [n]."""

    n: int
    chunk: Chunk
    distance: float


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class RetrievalResponse(BaseModel):
    route: RouteResult
    sources: list[RetrievedChunk]


# ---------- fit dashboard ----------

MatchStatus = Literal["match", "partial", "missing"]


class SkillMatchItem(BaseModel):
    """LLM output: how the resume covers ONE job skill, referenced by index."""

    job_skill: int = Field(description="Index of the job skill from the numbered job list.")
    status: MatchStatus = Field(description="match: the resume clearly shows it (same skill or a clear synonym). partial: related or weaker evidence. missing: nothing relevant.")
    resume_skills: list[int] = Field(description="Indexes of resume skills that provide the evidence; empty when missing.")
    note: str = Field(description="One short clause (max ~15 words) explaining the judgement.")


class SkillMatchResult(BaseModel):
    items: list[SkillMatchItem]


class SkillFit(BaseModel):
    name: str
    category: SkillCategory
    importance: Importance
    emphasis: Emphasis
    status: MatchStatus
    weight: float
    job_evidence: str
    resume_skills: list[str]
    resume_evidence: list[str]
    note: str


class ExperienceFit(BaseModel):
    required_years: float | None
    candidate_years: float | None
    met: bool | None


class FitCounts(BaseModel):
    required_total: int
    required_matched: int
    required_partial: int
    preferred_total: int
    preferred_matched: int
    preferred_partial: int


Verdict = Literal["strong", "good", "stretch", "weak"]


class FitReport(BaseModel):
    job_id: str
    job_label: str
    job_number: int | None
    title: str | None
    company: str | None
    seniority: Seniority
    score: int
    verdict: Verdict
    verdict_text: str
    experience: ExperienceFit
    counts: FitCounts
    matched: list[SkillFit]
    partial: list[SkillFit]
    missing: list[SkillFit]
