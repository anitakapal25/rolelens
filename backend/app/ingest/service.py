"""Ingestion use case: validate -> parse -> chunk -> store. Called by the API and by scripts."""

import logging
import uuid

from app.config import Settings
from app.ingest.chunking import chunk_document
from app.ingest.parse import parse_document
from app.ingest.registry import DocumentRegistry
from app.models import DocType, DocumentSummary

logger = logging.getLogger(__name__)


def default_label(doc_type: DocType, job_number: int | None) -> str:
    return "Resume" if doc_type == "resume" else f"Job #{job_number}"


def ingest_document(
    registry: DocumentRegistry,
    settings: Settings,
    filename: str,
    data: bytes,
    doc_type: DocType,
    label: str | None = None,
) -> DocumentSummary:
    """Parse, chunk and register one uploaded document.

    Scope is one resume: uploading a new resume replaces the previous one.
    """
    parsed = parse_document(filename, data, settings.max_upload_bytes, settings.max_pdf_pages)

    if doc_type == "resume":
        for old_id in registry.resume_ids():
            registry.delete(old_id)
            logger.info("replaced previous resume", extra={"doc_id": old_id})

    doc_id = uuid.uuid4().hex[:12]
    job_number = registry.next_job_number() if doc_type == "job" else None
    clean_label = (label or "").strip()
    final_label = clean_label or default_label(doc_type, job_number)

    chunks = chunk_document(
        doc_id=doc_id,
        doc_type=doc_type,
        doc_label=final_label,
        text=parsed.text,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    summary = registry.add_document(
        doc_id=doc_id,
        doc_type=doc_type,
        label=final_label,
        label_is_custom=bool(clean_label),
        job_number=job_number,
        filename=filename,
        page_count=parsed.page_count,
        raw_text=parsed.text,
        chunks=chunks,
    )
    logger.info(
        "ingested document",
        extra={"doc_id": doc_id, "doc_type": doc_type, "chunks": len(chunks)},
    )
    return summary
