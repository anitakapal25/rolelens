"""Chroma vector store: a derived search index over the chunks held in the SQLite registry.

Embeddings are computed by us (OpenAI) and passed in, so Chroma never embeds anything itself.
Distance is cosine: 0 = same direction, 2 = opposite.
"""

import logging
from typing import Any, Protocol

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.errors import ChromaError
from pydantic import BaseModel

from app.models import Chunk

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    pass


class ScoredChunk(BaseModel):
    chunk: Chunk
    distance: float


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...
    def delete_document(self, doc_id: str) -> None: ...
    def update_label(self, doc_id: str, label: str) -> None: ...
    def query(self, embedding: list[float], doc_id: str, k: int) -> list[ScoredChunk]: ...
    def count(self) -> int: ...
    def reset(self) -> None: ...


def chunk_metadata(chunk: Chunk) -> dict[str, str | int]:
    """Chroma metadata values must be str/int/float/bool, never None: drop empty fields."""
    raw: dict[str, Any] = chunk.model_dump(exclude={"text", "chunk_id"})
    return {k: v for k, v in raw.items() if v is not None}


def chunk_from_record(chunk_id: str, text: str, metadata: dict[str, Any]) -> Chunk:
    return Chunk(chunk_id=chunk_id, text=text, **metadata)


class ChromaStore:
    """Connects lazily, so the API can start (and report errors clearly) while Chroma is down."""

    def __init__(self, host: str, port: int, collection: str) -> None:
        self.host, self.port, self.collection_name = host, port, collection
        self._client: ClientAPI | None = None
        self._collection: Collection | None = None

    def _col(self) -> Collection:
        if self._collection is None:
            try:
                self._client = chromadb.HttpClient(host=self.host, port=self.port)
                self._collection = self._client.get_or_create_collection(
                    self.collection_name,
                    configuration={"hnsw": {"space": "cosine"}},
                    embedding_function=None,
                )
            except (ChromaError, ValueError, ConnectionError) as exc:
                raise VectorStoreError(f"Vector DB unavailable at {self.host}:{self.port}.") from exc
        return self._collection

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        try:
            self._col().upsert(
                ids=[c.chunk_id for c in chunks],
                embeddings=embeddings,  # type: ignore[arg-type]
                documents=[c.text for c in chunks],
                metadatas=[chunk_metadata(c) for c in chunks],  # type: ignore[misc]
            )
        except (ChromaError, ValueError) as exc:
            raise VectorStoreError("Failed to write to the vector DB.") from exc

    def delete_document(self, doc_id: str) -> None:
        try:
            self._col().delete(where={"doc_id": doc_id})
        except (ChromaError, ValueError) as exc:
            raise VectorStoreError("Failed to delete from the vector DB.") from exc

    def update_label(self, doc_id: str, label: str) -> None:
        col = self._col()
        try:
            ids = col.get(where={"doc_id": doc_id}, include=[])["ids"]
            if ids:
                col.update(ids=ids, metadatas=[{"doc_label": label}] * len(ids))
        except (ChromaError, ValueError) as exc:
            raise VectorStoreError("Failed to update the vector DB.") from exc

    def query(self, embedding: list[float], doc_id: str, k: int) -> list[ScoredChunk]:
        """Top-k nearest chunks restricted to one document (metadata filter)."""
        try:
            res = self._col().query(
                query_embeddings=[embedding],  # type: ignore[arg-type]
                n_results=k,
                where={"doc_id": doc_id},
                include=["documents", "metadatas", "distances"],
            )
        except (ChromaError, ValueError) as exc:
            raise VectorStoreError("Vector search failed.") from exc
        ids, docs = res["ids"][0], (res["documents"] or [[]])[0]
        metas, dists = (res["metadatas"] or [[]])[0], (res["distances"] or [[]])[0]
        return [
            ScoredChunk(chunk=chunk_from_record(i, d, dict(m)), distance=float(dist))
            for i, d, m, dist in zip(ids, docs, metas, dists, strict=True)
        ]

    def count(self) -> int:
        return self._col().count()

    def reset(self) -> None:
        """Drop and recreate the collection (used by reindex)."""
        self._col()
        assert self._client is not None
        try:
            self._client.delete_collection(self.collection_name)
        except (ChromaError, ValueError) as exc:
            raise VectorStoreError("Failed to reset the vector DB.") from exc
        self._collection = None
        self._col()
