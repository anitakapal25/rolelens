"""Document-filtered retrieval: top-k PER DOCUMENT, not global top-k.

Why per document: a global top-12 over "resume + 3 jobs" is easily filled by one long, wordy job
description, so the resume (the other half of every fit question) can vanish from the context.
Querying each routed document separately guarantees every routed document is represented.

Selection per document:
- take the k nearest chunks (cosine distance) within that document only (metadata filter);
- drop chunks farther than max_distance, but ALWAYS keep the single best one, so a routed document is
  never silently missing from the answer's context.

Ordering for the prompt: resume first, then jobs by job number; within a document, by relevance.
Chunks are numbered 1..n in that order; the numbers are what the answer cites as [n].
"""

from collections.abc import Callable

from app.models import RetrievedChunk
from app.retrieval.embed import Embedder
from app.retrieval.store import ScoredChunk, VectorStore


def select_for_document(hits: list[ScoredChunk], k: int, max_distance: float) -> list[ScoredChunk]:
    """Pure: nearest-first hits of ONE document -> the ones to keep."""
    ranked = sorted(hits, key=lambda h: h.distance)[:k]
    if not ranked:
        return []
    return [ranked[0]] + [h for h in ranked[1:] if h.distance <= max_distance]


def number_chunks(per_doc: list[list[ScoredChunk]]) -> list[RetrievedChunk]:
    """Pure: flatten per-document selections (already in document order) and number them 1..n."""
    flat = [hit for doc_hits in per_doc for hit in doc_hits]
    return [RetrievedChunk(n=i, chunk=h.chunk, distance=round(h.distance, 4)) for i, h in enumerate(flat, start=1)]


def retrieve(
    question: str,
    doc_ids: list[str],
    embedder: Embedder,
    store: VectorStore,
    k_for: Callable[[str], int],
    max_distance: float,
    doc_order: Callable[[str], tuple[int, int]],
) -> list[RetrievedChunk]:
    """Embed the question once, search each routed document separately, then merge.

    k_for(doc_id) gives that document's k (the resume gets a larger one).
    """
    if not doc_ids:
        return []
    vectors, _ = embedder.embed([question])
    query = vectors[0]
    per_doc = [
        select_for_document(store.query(query, doc_id, k_for(doc_id)), k_for(doc_id), max_distance)
        for doc_id in sorted(doc_ids, key=doc_order)
    ]
    return number_chunks(per_doc)
