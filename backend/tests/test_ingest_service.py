"""Ingestion is atomic: a failure in any remote step leaves nothing behind."""

import pytest

from app.config import Settings
from app.ingest.service import ingest_document
from app.llm.client import LLMError
from app.main import build_services
from app.retrieval.embed import EmbeddingError
from app.retrieval.store import VectorStoreError
from tests.fakes import FakeEmbedder, FakeLLM, InMemoryStore


def test_success_stores_registry_extraction_and_vectors(settings: Settings, job_text: str) -> None:
    store = InMemoryStore()
    svc = build_services(settings, llm=FakeLLM(), embedder=FakeEmbedder(), store=store)
    doc = ingest_document(svc, "job.txt", job_text.encode(), "job")
    assert store.count() == doc.chunk_count > 0
    _, extraction = svc.registry.get_extraction(doc.doc_id)
    assert extraction is not None and extraction["company"] == "Initech Inc."


def test_llm_failure_stores_nothing(settings: Settings, job_text: str) -> None:
    store = InMemoryStore()
    embedder = FakeEmbedder()
    svc = build_services(settings, llm=FakeLLM(fail=LLMError("down", retryable=True)), embedder=embedder, store=store)
    with pytest.raises(LLMError):
        ingest_document(svc, "job.txt", job_text.encode(), "job")
    assert svc.registry.list_summaries() == [] and store.count() == 0
    assert embedder.calls == []  # never paid for embeddings after the LLM failed


def test_embedding_failure_stores_nothing(settings: Settings, job_text: str) -> None:
    svc = build_services(settings, llm=FakeLLM(), embedder=FakeEmbedder(fail=True), store=InMemoryStore())
    with pytest.raises(EmbeddingError):
        ingest_document(svc, "job.txt", job_text.encode(), "job")
    assert svc.registry.list_summaries() == []


def test_store_failure_rolls_back_registry(settings: Settings, job_text: str) -> None:
    svc = build_services(settings, llm=FakeLLM(), embedder=FakeEmbedder(), store=InMemoryStore(fail_upsert=True))
    with pytest.raises(VectorStoreError):
        ingest_document(svc, "job.txt", job_text.encode(), "job")
    assert svc.registry.list_summaries() == []


def test_failed_resume_upload_keeps_previous_resume(settings: Settings, resume_text: str) -> None:
    store = InMemoryStore()
    good = build_services(settings, llm=FakeLLM(), embedder=FakeEmbedder(), store=store)
    first = ingest_document(good, "cv1.txt", resume_text.encode(), "resume")
    bad = build_services(settings, llm=FakeLLM(), embedder=FakeEmbedder(fail=True), store=store)
    with pytest.raises(EmbeddingError):
        ingest_document(bad, "cv2.txt", resume_text.encode(), "resume")
    assert [d.doc_id for d in good.registry.list_summaries()] == [first.doc_id]
    assert store.doc_ids() == {first.doc_id}


def test_new_resume_replaces_old_vectors(settings: Settings, resume_text: str) -> None:
    store = InMemoryStore()
    svc = build_services(settings, llm=FakeLLM(), embedder=FakeEmbedder(), store=store)
    ingest_document(svc, "cv1.txt", resume_text.encode(), "resume")
    second = ingest_document(svc, "cv2.txt", resume_text.encode(), "resume")
    assert store.doc_ids() == {second.doc_id}


def test_custom_label_beats_auto_label(settings: Settings, job_text: str) -> None:
    svc = build_services(settings, llm=FakeLLM(), embedder=FakeEmbedder(), store=InMemoryStore())
    doc = ingest_document(svc, "job.txt", job_text.encode(), "job", label="My dream job")
    assert doc.label == "My dream job"
