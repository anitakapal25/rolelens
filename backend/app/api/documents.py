"""Document routes. Thin: parse the request, call a service, return a model."""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status

from app.api.deps import ServicesDep
from app.demo.limits import enforce_limit, require_writable
from app.ingest import service
from app.ingest.extraction import parse_extraction
from app.ingest.registry import DocumentNotFound
from app.models import Chunk, DocType, DocumentSummary, ErrorResponse, Extraction, RenameRequest

router = APIRouter(prefix="/documents", tags=["documents"])

NOT_FOUND = {404: {"model": ErrorResponse}}
UPSTREAM = {502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


def _not_found(exc: DocumentNotFound) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")


# Sync handler on purpose: ingestion makes blocking SDK calls, and FastAPI runs sync handlers
# in a threadpool so they don't block the event loop.
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
               429: {"model": ErrorResponse}, **UPSTREAM},
)
def upload_document(
    svc: ServicesDep,
    request: Request,
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[DocType, Form()],
    label: Annotated[str | None, Form(max_length=80)] = None,
) -> DocumentSummary:
    require_writable(svc.settings)
    enforce_limit(svc.upload_limiter, request)
    data = file.file.read(svc.settings.max_upload_bytes + 1)  # at most one byte past the cap
    return service.ingest_document(svc, file.filename or "upload", data, doc_type, label)


@router.get("")
def list_documents(svc: ServicesDep) -> list[DocumentSummary]:
    return svc.registry.list_summaries()


@router.post("/reindex", responses=UPSTREAM)
def reindex(svc: ServicesDep) -> service.ReindexResult:
    require_writable(svc.settings)
    return service.reindex_all(svc)


@router.get("/{doc_id}/chunks", responses=NOT_FOUND)
def get_document_chunks(doc_id: str, svc: ServicesDep) -> list[Chunk]:
    try:
        return svc.registry.get_chunks(doc_id)
    except DocumentNotFound as exc:
        raise _not_found(exc) from exc


@router.get("/{doc_id}/extraction", responses=NOT_FOUND)
def get_document_extraction(doc_id: str, svc: ServicesDep) -> Extraction:
    try:
        doc_type, data = svc.registry.get_extraction(doc_id)
    except DocumentNotFound as exc:
        raise _not_found(exc) from exc
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No extraction stored for this document.")
    return parse_extraction(doc_type, data)


@router.patch("/{doc_id}", responses=NOT_FOUND)
def rename_document(doc_id: str, body: RenameRequest, svc: ServicesDep) -> DocumentSummary:
    require_writable(svc.settings)
    try:
        return service.rename_document(svc, doc_id, body.label.strip())
    except DocumentNotFound as exc:
        raise _not_found(exc) from exc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
def delete_document(doc_id: str, svc: ServicesDep) -> Response:
    require_writable(svc.settings)
    try:
        service.delete_document(svc, doc_id)
    except DocumentNotFound as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
