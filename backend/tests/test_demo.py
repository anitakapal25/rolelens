"""Free-tier demo: in-memory store, seed loading, read-only guard, rate limits, single-service app."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo.limits import RateLimiter
from app.demo.seed import load_seed, read_seed
from app.ingest.registry import DocumentRegistry
from app.main import build_services, create_app
from app.models import Chunk, Usage
from app.retrieval.store import MemoryStore
from tests.fakes import FakeLLM


class SeedSizedEmbedder:
    """Returns vectors with the seed's dimensionality (1536)."""

    def embed(self, texts: list[str]) -> tuple[list[list[float]], Usage]:
        return [[1.0] * 1536 for _ in texts], Usage(model="fake", input_tokens=0, output_tokens=0, cost_usd=0)


def chunk(doc_id: str, i: int) -> Chunk:
    return Chunk(chunk_id=f"{doc_id}:{i}", doc_id=doc_id, doc_type="job", doc_label=doc_id,
                 section="requirements", index=i, text=f"text {i}")


# ----- MemoryStore -----

def test_memory_store_filters_by_document_and_ranks_by_cosine() -> None:
    store = MemoryStore()
    store.upsert([chunk("a", 0), chunk("a", 1), chunk("b", 0)], [[1, 0], [0.6, 0.8], [1, 0]])
    hits = store.query([1, 0], "a", k=5)
    assert [h.chunk.chunk_id for h in hits] == ["a:0", "a:1"]
    assert hits[0].distance == pytest.approx(0.0) and hits[1].distance == pytest.approx(0.4)
    store.update_label("a", "Renamed")
    assert all(h.chunk.doc_label == "Renamed" for h in store.query([1, 0], "a", 5))
    store.delete_document("a")
    assert store.count() == 1 and store.query([1, 0], "a", 5) == []


# ----- rate limiter -----

def test_rate_limiter_per_ip_window_and_daily_cap() -> None:
    limiter = RateLimiter(per_ip_hour=2, daily_limit=3)
    t = 1_000_000.0
    assert limiter.check("1.1.1.1", t) is None
    assert limiter.check("1.1.1.1", t + 1) is None
    assert "per hour" in (limiter.check("1.1.1.1", t + 2) or "")       # third in the hour: blocked
    assert limiter.check("2.2.2.2", t + 3) is None                     # other IP fine (3rd today)
    assert "today" in (limiter.check("3.3.3.3", t + 4) or "")          # daily cap reached
    assert limiter.check("1.1.1.1", t + 3601 + 86400) is None          # next day, window expired


# ----- seed -----

def test_committed_seed_is_sample_data_only() -> None:
    seed = read_seed()
    assert [d.doc_type for d in seed.documents].count("resume") == 1
    assert {d.filename for d in seed.documents} == {
        "resume_jordan_rivera.txt", "job1_meridian_health.txt", "job2_lumen_labs.txt", "job3_brightwave.txt"}
    assert all(len(d.vectors) == len(d.chunks) for d in seed.documents)


def test_load_seed_fills_registry_and_store_independently(tmp_path: Path) -> None:
    seed = read_seed()
    settings = Settings(registry_db_path=tmp_path / "r.sqlite3", _env_file=None)
    first = build_services(settings, llm=FakeLLM(), embedder=SeedSizedEmbedder(), store=MemoryStore())
    assert load_seed(first, seed) == 4 and first.store.count() == 22
    # A second app in the same process shares the SQLite file but has its own empty in-memory store.
    second = build_services(settings, llm=FakeLLM(), embedder=SeedSizedEmbedder(), store=MemoryStore())
    assert load_seed(second, seed) == 0 and second.store.count() == 22
    assert DocumentRegistry(settings.registry_db_path).reserve_job_number() == 4  # counter continues


# ----- demo app -----

@pytest.fixture
def demo(tmp_path: Path) -> tuple[TestClient, FakeLLM]:
    settings = Settings(registry_db_path=tmp_path / "r.sqlite3", demo_mode=True, vector_store="memory",
                        demo_rate_per_ip_hour=2, _env_file=None)
    llm = FakeLLM()
    services = build_services(settings, llm=llm, embedder=SeedSizedEmbedder(), store=MemoryStore())
    return TestClient(create_app(settings, services)), llm


def test_demo_starts_seeded_and_read_only(demo: tuple[TestClient, FakeLLM]) -> None:
    client, _ = demo
    assert client.get("/config").json()["demo"] is True
    docs = client.get("/documents").json()
    assert len(docs) == 4 and any(d["warnings"] for d in docs)
    job = next(d for d in docs if d["doc_type"] == "job")
    upload = client.post("/documents", files={"file": ("x.txt", b"Requirements\nPython")}, data={"doc_type": "job"})
    assert upload.status_code == 403 and "read-only" in upload.json()["detail"]
    assert client.patch(f"/documents/{job['doc_id']}", json={"label": "x"}).status_code == 403
    assert client.delete(f"/documents/{job['doc_id']}").status_code == 403
    assert client.post("/documents/reindex").status_code == 403


def test_demo_fit_uses_seeded_matches_without_llm(demo: tuple[TestClient, FakeLLM]) -> None:
    client, llm = demo
    fits = client.get("/fit").json()
    assert len(fits) == 3 and all(f["matched"] or f["partial"] or f["missing"] for f in fits)
    assert not any(c.get("schema").__name__ == "SkillMatchResult" for c in llm.calls if "schema" in c)


def test_demo_chat_is_rate_limited_per_ip(demo: tuple[TestClient, FakeLLM]) -> None:
    client, _ = demo
    headers = {"X-Forwarded-For": "203.0.113.7"}
    for _ in range(2):
        assert client.post("/chat", json={"question": "Which role fits me best?"}, headers=headers).status_code == 200
    blocked = client.post("/chat", json={"question": "Which role fits me best?"}, headers=headers)
    assert blocked.status_code == 429 and "per hour" in blocked.json()["detail"]
    other = client.post("/chat", json={"question": "Which role fits me best?"}, headers={"X-Forwarded-For": "198.51.100.1"})
    assert other.status_code == 200


def test_rate_limit_without_demo_keeps_uploads_but_limits_them(tmp_path: Path) -> None:
    """RATE_LIMIT=true on a public instance with uploads: writable, but uploads and chat are capped per IP."""
    settings = Settings(registry_db_path=tmp_path / "r.sqlite3", vector_store="memory", rate_limit=True,
                        upload_rate_per_ip_hour=1, demo_rate_per_ip_hour=1, _env_file=None)
    services = build_services(settings, llm=FakeLLM(), embedder=SeedSizedEmbedder(), store=MemoryStore())
    client = TestClient(create_app(settings, services))
    ip = {"X-Forwarded-For": "203.0.113.9"}
    resume = b"Jordan Rivera\nExperience\nSenior Engineer, Northstar\n- Built Python services"

    first = client.post("/documents", files={"file": ("cv.txt", resume)}, data={"doc_type": "resume"}, headers=ip)
    assert first.status_code == 201
    second = client.post("/documents", files={"file": ("cv.txt", resume)}, data={"doc_type": "resume"}, headers=ip)
    assert second.status_code == 429 and "uploads per hour" in second.json()["detail"]

    assert client.post("/chat/retrieve", json={"question": "Where do I work?"}, headers=ip).status_code == 200
    blocked = client.post("/chat/retrieve", json={"question": "Where do I work?"}, headers=ip)
    assert blocked.status_code == 429 and "questions per hour" in blocked.json()["detail"]


def test_non_demo_has_no_limits_and_is_writable(client: TestClient) -> None:
    assert client.get("/config").json()["demo"] is False
    for _ in range(20):
        assert client.post("/chat/retrieve", json={"question": "Which role fits me best?"}).status_code == 200


# ----- single-service app (API under /api, frontend at /) -----

def test_serving_app_mounts_api_and_static(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>RoleLens</title>")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    monkeypatch.setenv("REGISTRY_DB_PATH", str(tmp_path / "r.sqlite3"))
    from app.serve import create_serving_app

    client = TestClient(create_serving_app(tmp_path))
    assert "RoleLens" in client.get("/").text
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/config").json()["demo"] is False
