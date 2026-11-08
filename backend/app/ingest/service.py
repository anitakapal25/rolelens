"""Document use cases: ingest, rename, delete, reindex.

Ingest order matters: every remote call that can fail (LLM extraction, embeddings) runs BEFORE
anything is written, so a failed upload leaves no half-indexed document behind.
"""

import logging
import uuid

from pydantic import BaseModel

from app.ingest.chunking import chunk_document
from app.ingest.extraction import auto_label, extract_structured
from app.ingest.parse import parse_document
from app.models import DocType, DocumentSummary
from app.retrieval.embed import embedding_text
from app.retrieval.store import VectorStoreError
from app.services import Services

logger = logging.getLogger(__name__)


class ReindexResult(BaseModel):
    documents: int
    chunks: int


def ingest_document(
    svc: Services, filename: str, data: bytes, doc_type: DocType, label: str | None = None
) -> DocumentSummary:
    s = svc.settings
    parsed = parse_document(filename, data, s.max_upload_bytes, s.max_pdf_pages)

    doc_id = uuid.uuid4().hex[:12]
    job_number = svc.registry.next_job_number() if doc_type == "job" else None

    # 1. Remote calls first (nothing persisted yet).
    extraction, extract_usage = extract_structured(svc.llm, s.fast_model, doc_type, parsed.text)
    custom_label = (label or "").strip()
    final_label = custom_label or auto_label(doc_type, job_number, extraction)

    chunks = chunk_document(doc_id, doc_type, final_label, parsed.text, s.chunk_max_chars, s.chunk_overlap_chars)
    vectors, embed_usage = svc.embedder.embed([embedding_text(c) for c in chunks])

    # 2. Persist: registry (source of truth), then the index; roll back the registry if indexing fails.
    old_resume_ids = svc.registry.resume_ids() if doc_type == "resume" else []
    summary = svc.registry.add_document(
        doc_id=doc_id, doc_type=doc_type, label=final_label, label_is_custom=bool(custom_label),
        job_number=job_number, filename=filename, page_count=parsed.page_count, raw_text=parsed.text,
        chunks=chunks, extraction=extraction.model_dump(),
    )
    try:
        svc.store.upsert(chunks, vectors)
    except VectorStoreError:
        svc.registry.delete(doc_id)
        raise

    # 3. One resume in scope: the new one replaces the old only after it is fully stored.
    for old_id in old_resume_ids:
        delete_document(svc, old_id)

    logger.info("ingested document", extra={
        "doc_id": doc_id, "doc_type": doc_type, "chunks": len(chunks),
        "cost_usd": round(extract_usage.cost_usd + embed_usage.cost_usd, 6),
    })
    return summary


def rename_document(svc: Services, doc_id: str, label: str) -> DocumentSummary:
    summary = svc.registry.rename(doc_id, label)
    try:
        svc.store.update_label(doc_id, label)
    except VectorStoreError:
        # The registry is the source of truth for labels; a stale index label is cosmetic.
        logger.warning("label not updated in vector store", extra={"doc_id": doc_id})
    return summary


def delete_document(svc: Services, doc_id: str) -> None:
    svc.registry.delete(doc_id)
    try:
        svc.store.delete_document(doc_id)
    except VectorStoreError:
        # Orphaned vectors are harmless: retrieval only queries doc_ids that exist in the registry.
        logger.warning("vectors not deleted; run reindex to clean up", extra={"doc_id": doc_id})


def reindex_all(svc: Services) -> ReindexResult:
    """Rebuild the vector index from the registry (e.g. after changing the embedding model)."""
    svc.store.reset()
    docs = svc.registry.list_summaries()
    total = 0
    for doc in docs:
        chunks = svc.registry.get_chunks(doc.doc_id)
        vectors, _ = svc.embedder.embed([embedding_text(c) for c in chunks])
        svc.store.upsert(chunks, vectors)
        total += len(chunks)
    return ReindexResult(documents=len(docs), chunks=total)
