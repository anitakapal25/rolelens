from fastapi.testclient import TestClient

from app.services import Services
from tests.fakes import InMemoryStore


def upload(client: TestClient, name: str, text: str, doc_type: str, label: str | None = None):
    data = {"doc_type": doc_type}
    if label:
        data["label"] = label
    return client.post("/documents", files={"file": (name, text.encode(), "text/plain")}, data=data)


def test_upload_returns_summary_with_sections(client: TestClient, job_text: str) -> None:
    res = upload(client, "job.txt", job_text, "job")
    assert res.status_code == 201
    body = res.json()
    assert body["label"] == "Job #1 — Senior Backend Engineer, Initech" and body["job_number"] == 1
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


def test_rename_and_delete(client: TestClient, services: Services, job_text: str) -> None:
    doc = upload(client, "job.txt", job_text, "job").json()
    store = services.store
    assert isinstance(store, InMemoryStore) and store.doc_ids() == {doc["doc_id"]}
    res = client.patch(f"/documents/{doc['doc_id']}", json={"label": "Initech"})
    assert res.json()["label"] == "Initech"
    chunks = client.get(f"/documents/{doc['doc_id']}/chunks").json()
    assert all(c["doc_label"] == "Initech" for c in chunks)
    assert all(c.doc_label == "Initech" for c, _ in store.items.values())
    assert client.delete(f"/documents/{doc['doc_id']}").status_code == 204
    assert client.get("/documents").json() == []
    assert store.doc_ids() == set()


def test_validation_errors_map_to_http_codes(client: TestClient) -> None:
    assert upload(client, "cv.png", "x", "resume").status_code == 400
    assert upload(client, "cv.txt", "x" * (1024 * 1024 + 1), "resume").status_code == 413
    assert upload(client, "cv.txt", "   ", "resume").status_code == 422
    assert upload(client, "cv.txt", "hello", "cover_letter").status_code == 422
    assert client.patch("/documents/missing", json={"label": "x"}).status_code == 404


def test_extraction_endpoint_returns_cached_extraction(client: TestClient, job_text: str) -> None:
    doc = upload(client, "job.txt", job_text, "job").json()
    body = client.get(f"/documents/{doc['doc_id']}/extraction").json()
    assert body["title"] == "Senior Backend Engineer"
    assert body["skills"][0]["importance"] == "required"


def test_reindex_rebuilds_vector_store(client: TestClient, services: Services, job_text: str, resume_text: str) -> None:
    upload(client, "job.txt", job_text, "job")
    upload(client, "cv.txt", resume_text, "resume")
    store = services.store
    assert isinstance(store, InMemoryStore)
    expected = store.count()
    store.reset()
    res = client.post("/documents/reindex").json()
    assert res == {"documents": 2, "chunks": expected} and store.count() == expected
