from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(registry_db_path=tmp_path / "registry.sqlite3", max_upload_mb=1, _env_file=None)
    return TestClient(create_app(settings))


def upload(client: TestClient, name: str, text: str, doc_type: str, label: str | None = None):
    data = {"doc_type": doc_type}
    if label:
        data["label"] = label
    return client.post("/documents", files={"file": (name, text.encode(), "text/plain")}, data=data)


def test_upload_returns_summary_with_sections(client: TestClient, job_text: str) -> None:
    res = upload(client, "job.txt", job_text, "job")
    assert res.status_code == 201
    body = res.json()
    assert body["label"] == "Job #1" and body["job_number"] == 1
    assert [s["name"] for s in body["sections"]] == ["overview", "responsibilities", "requirements", "preferred"]
    assert body["chunk_count"] == 4


def test_job_numbers_increment_and_custom_label_kept(client: TestClient, job_text: str) -> None:
    upload(client, "a.txt", job_text, "job")
    res = upload(client, "b.txt", job_text, "job", label="Initech backend")
    assert res.json()["job_number"] == 2
    assert res.json()["label"] == "Initech backend"


def test_new_resume_replaces_old(client: TestClient, resume_text: str) -> None:
    first = upload(client, "cv1.txt", resume_text, "resume").json()
    upload(client, "cv2.txt", resume_text, "resume")
    docs = client.get("/documents").json()
    assert [d["filename"] for d in docs if d["doc_type"] == "resume"] == ["cv2.txt"]
    assert client.get(f"/documents/{first['doc_id']}/chunks").status_code == 404


def test_chunks_endpoint_returns_metadata(client: TestClient, resume_text: str) -> None:
    doc = upload(client, "cv.txt", resume_text, "resume").json()
    chunks = client.get(f"/documents/{doc['doc_id']}/chunks").json()
    assert any(c["company"] == "Globex" for c in chunks)


def test_rename_and_delete(client: TestClient, job_text: str) -> None:
    doc = upload(client, "job.txt", job_text, "job").json()
    res = client.patch(f"/documents/{doc['doc_id']}", json={"label": "Initech"})
    assert res.json()["label"] == "Initech"
    chunks = client.get(f"/documents/{doc['doc_id']}/chunks").json()
    assert all(c["doc_label"] == "Initech" for c in chunks)
    assert client.delete(f"/documents/{doc['doc_id']}").status_code == 204
    assert client.get("/documents").json() == []


def test_validation_errors_map_to_http_codes(client: TestClient) -> None:
    assert upload(client, "cv.png", "x", "resume").status_code == 400
    assert upload(client, "cv.txt", "x" * (1024 * 1024 + 1), "resume").status_code == 413
    assert upload(client, "cv.txt", "   ", "resume").status_code == 422
    assert upload(client, "cv.txt", "hello", "cover_letter").status_code == 422
    assert client.patch("/documents/missing", json={"label": "x"}).status_code == 404
