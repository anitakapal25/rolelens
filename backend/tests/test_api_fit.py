from fastapi.testclient import TestClient

from app.services import Services
from tests.fakes import FakeLLM


def upload(client: TestClient, name: str, text: str, doc_type: str) -> str:
    res = client.post("/documents", files={"file": (name, text.encode())}, data={"doc_type": doc_type})
    return res.json()["doc_id"]


def test_fit_requires_a_resume(client: TestClient, job_text: str) -> None:
    job_id = upload(client, "j.txt", job_text, "job")
    assert client.get("/fit").status_code == 409
    assert client.get(f"/fit/{job_id}").json()["detail"] == "Upload your resume to see fit scores."


def test_fit_report_and_cache(client: TestClient, services: Services, resume_text: str, job_text: str) -> None:
    upload(client, "cv.txt", resume_text, "resume")
    job_id = upload(client, "j.txt", job_text, "job")
    llm = services.llm
    assert isinstance(llm, FakeLLM)
    calls_before = len(llm.calls)

    report = client.get(f"/fit/{job_id}").json()
    # Fake: one required core skill (Python) matched; job asks 5 yrs, resume shows 6 -> experience met.
    assert report["score"] == 100 and report["verdict"] == "strong"
    assert report["matched"][0]["name"] == "Python"
    assert report["matched"][0]["resume_evidence"] == ["Python, FastAPI"]
    # Years come from the fixture's dated roles (Mar 2018 - Present), not the fake extraction's 6.
    exp = report["experience"]
    assert exp["required_years"] == 5 and exp["met"] is True and exp["candidate_years"] >= 7.8
    assert report["job_label"].startswith("Job #1")

    client.get(f"/fit/{job_id}")
    assert client.get("/fit").json()[0]["job_id"] == job_id
    assert len(llm.calls) == calls_before + 1  # matched once, then served from cache


def test_new_resume_invalidates_cache(client: TestClient, services: Services, resume_text: str, job_text: str) -> None:
    upload(client, "cv.txt", resume_text, "resume")
    job_id = upload(client, "j.txt", job_text, "job")
    client.get(f"/fit/{job_id}")
    llm = services.llm
    assert isinstance(llm, FakeLLM)
    upload(client, "cv2.txt", resume_text, "resume")   # new resume doc_id
    n = len(llm.calls)
    client.get(f"/fit/{job_id}")
    assert len(llm.calls) == n + 1


def test_fit_404s(client: TestClient, resume_text: str) -> None:
    resume_id = upload(client, "cv.txt", resume_text, "resume")
    assert client.get("/fit/nope").status_code == 404
    assert client.get(f"/fit/{resume_id}").status_code == 404  # a resume is not a job
