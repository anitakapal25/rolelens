"""Test doubles that implement the LLMClient, Embedder and VectorStore protocols."""

import hashlib
import math
from collections.abc import Iterator
from typing import Any, TypeVar

from anthropic.types import MessageParam
from pydantic import BaseModel

from app.llm.client import LLMError, StreamDone, StreamEvent, TextDelta
from app.llm.pricing import make_usage
from app.models import Chunk, JobExtraction, JobSkill, ResumeExtraction, ResumeSkill, Usage
from app.retrieval.embed import EmbeddingError
from app.retrieval.store import ScoredChunk, VectorStoreError

T = TypeVar("T", bound=BaseModel)

RESUME_EXTRACTION = ResumeExtraction(
    candidate_name="Jane Doe", headline="Backend Engineer", total_years_experience=6,
    skills=[ResumeSkill(name="Python", category="language", years=6, evidence="Python, FastAPI")],
)
JOB_EXTRACTION = JobExtraction(
    title="Senior Backend Engineer", company="Initech Inc.", seniority="senior", min_years_experience=5,
    skills=[JobSkill(name="Python", category="language", importance="required", emphasis="core",
                     min_years=5, evidence="5+ years of Python.")],
)


class FakeLLM:
    def __init__(self, fail: LLMError | None = None, answer: str = "Fake answer [1].") -> None:
        self.fail = fail
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def extract(self, *, model: str, system: str, user: str, schema: type[T], effort: str = "low",
                max_tokens: int = 16000) -> tuple[T, Usage]:
        self.calls.append({"model": model, "system": system, "user": user, "schema": schema})
        if self.fail:
            raise self.fail
        canned = RESUME_EXTRACTION if schema is ResumeExtraction else JOB_EXTRACTION
        return schema.model_validate(canned.model_dump()), make_usage(model, 100, 50)

    def stream_text(self, *, model: str, system: str, messages: list[MessageParam], effort: str = "low",
                    max_tokens: int = 8000) -> Iterator[StreamEvent]:
        self.calls.append({"model": model, "system": system, "messages": messages})
        for word in self.answer.split(" "):
            yield TextDelta(word + " ")
        yield StreamDone(usage=make_usage(model, 100, 20), stop_reason="end_turn")


def fake_vector(text: str, dims: int = 16) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    vec = [b / 255 for b in digest[:dims]]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeEmbedder:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> tuple[list[list[float]], Usage]:
        self.calls.append(texts)
        if self.fail:
            raise EmbeddingError("embedding down")
        return [fake_vector(t) for t in texts], make_usage("text-embedding-3-small", 10 * len(texts), 0)


class InMemoryStore:
    def __init__(self, fail_upsert: bool = False) -> None:
        self.items: dict[str, tuple[Chunk, list[float]]] = {}
        self.fail_upsert = fail_upsert

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if self.fail_upsert:
            raise VectorStoreError("store down")
        for c, e in zip(chunks, embeddings, strict=True):
            self.items[c.chunk_id] = (c, e)

    def delete_document(self, doc_id: str) -> None:
        self.items = {k: v for k, v in self.items.items() if v[0].doc_id != doc_id}

    def update_label(self, doc_id: str, label: str) -> None:
        for k, (c, e) in list(self.items.items()):
            if c.doc_id == doc_id:
                self.items[k] = (c.model_copy(update={"doc_label": label}), e)

    def query(self, embedding: list[float], doc_id: str, k: int) -> list[ScoredChunk]:
        scored = [
            ScoredChunk(chunk=c, distance=1 - sum(a * b for a, b in zip(embedding, e, strict=True)))
            for c, e in self.items.values() if c.doc_id == doc_id
        ]
        return sorted(scored, key=lambda s: s.distance)[:k]

    def count(self) -> int:
        return len(self.items)

    def reset(self) -> None:
        self.items = {}

    def doc_ids(self) -> set[str]:
        return {c.doc_id for c, _ in self.items.values()}
