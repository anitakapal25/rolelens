import pytest

from app.llm.client import LLMError
from app.models import RouteDecision
from app.retrieval.router import DocRef, keyword_route, route_question
from tests.fakes import FakeLLM

RESUME = DocRef(doc_id="r", doc_type="resume", label="Resume — Jane")
JOB1 = DocRef(doc_id="j1", doc_type="job", label="Job #1 — FDE, HCLTech", job_number=1,
              title="Forward Deployed Engineer", company="HCLTech")
JOB2 = DocRef(doc_id="j2", doc_type="job", label="Job #2 — Senior FDE, Platinus", job_number=2,
              title="Senior Forward Deployed Engineer", company="Platinus Technologies Pvt. Ltd.")
JOB3 = DocRef(doc_id="j3", doc_type="job", label="Job #3", job_number=3, title="Forward Deployment Engineer")
DOCS = [RESUME, JOB1, JOB2, JOB3]


@pytest.mark.parametrize("question", [
    "What does Job #2 require?",
    "what does job 2 need",
    "Am I a fit for the second role?",
    "How do I prepare for the Platinus interview?",
    "Is the platinus role remote?",
])
def test_explicit_job_two_routes_to_job_two_plus_resume(question: str) -> None:
    result = keyword_route(question, DOCS)
    assert result is not None and result.method == "keyword"
    assert result.doc_ids == ["r", "j2"]


def test_two_named_jobs() -> None:
    result = keyword_route("Compare job 1 and job 3", DOCS)
    assert result is not None and result.doc_ids == ["r", "j1", "j3"]


@pytest.mark.parametrize("question", [
    "Which role fits me best?",
    "How do I compare across these roles?",
    "Rank the jobs by fit",
])
def test_comparative_questions_route_to_everything(question: str) -> None:
    result = keyword_route(question, DOCS)
    assert result is not None and result.scope == "all_jobs"
    assert result.doc_ids == ["r", "j1", "j2", "j3"]


def test_resume_only() -> None:
    result = keyword_route("Summarise my resume in three bullets", DOCS)
    assert result is not None and result.doc_ids == ["r"]


def test_resume_question_mentioning_jobs_is_not_resume_only() -> None:
    assert keyword_route("What skills in my resume are missing for these jobs?", DOCS) is not None
    assert keyword_route("Does my resume show the requirements?", DOCS) is None  # unsure -> LLM


def test_unknown_job_number_includes_everything() -> None:
    result = keyword_route("What does Job #7 require?", DOCS)
    assert result is not None and result.doc_ids == ["r", "j1", "j2", "j3"]


def test_ambiguous_question_returns_none() -> None:
    assert keyword_route("What skills am I missing?", DOCS) is None


def test_llm_route_used_when_rules_unsure() -> None:
    llm = FakeLLM(route=RouteDecision(scope="specific_jobs", job_numbers=[1]))
    result = route_question("Do I have the healthcare background they want?", DOCS, llm, "haiku")
    assert result.method == "llm" and result.doc_ids == ["r", "j1"]
    assert "Job #1" in llm.calls[0]["user"] and "HCLTech" in llm.calls[0]["user"]


def test_llm_route_with_unknown_numbers_widens_to_all() -> None:
    llm = FakeLLM(route=RouteDecision(scope="specific_jobs", job_numbers=[9]))
    assert route_question("the robotics one?", DOCS, llm, "haiku").doc_ids == ["r", "j1", "j2", "j3"]


def test_llm_failure_falls_back_to_all_documents() -> None:
    llm = FakeLLM(fail=LLMError("down", retryable=True))
    result = route_question("What skills am I missing?", DOCS, llm, "haiku")
    assert result.method == "fallback" and set(result.doc_ids) == {"r", "j1", "j2", "j3"}


def test_no_documents_and_resume_only_uploads() -> None:
    llm = FakeLLM()
    assert route_question("anything", [], llm, "haiku").method == "empty"
    only_resume = route_question("What am I good at?", [RESUME], llm, "haiku")
    assert only_resume.doc_ids == ["r"] and llm.calls == []
