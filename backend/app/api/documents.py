"""Document routes. Thin: parse the request, call a service, return a model."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status

from app.config import Settings, get_settings
from app.ingest.registry import DocumentNotFound, DocumentRegistry
from app.ingest.service import ingest_document
from app.models import Chunk, DocType, DocumentSummary, ErrorResponse, RenameRequest

router = APIRouter(prefix="/documents", tags=["documents"])


def get_registry(request: Request) -> DocumentRegistry:
    registry: DocumentRegistry = request.app.state.registry
    return registry


RegistryDep = Annotated[DocumentRegistry, Depends(get_registry)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def upload_document(
    registry: RegistryDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[DocType, Form()],
    label: Annotated[str | None, Form(max_length=80)] = None,
) -> DocumentSummary:
    data = await file.read(settings.max_upload_bytes + 1)  # read at most one byte past the cap
    return ingest_document(registry, settings, file.filename or "upload", data, doc_type, label)


@router.get("")
def list_documents(registry: RegistryDep) -> list[DocumentSummary]:
    return registry.list_summaries()


@router.get("/{doc_id}/chunks", responses={404: {"model": ErrorResponse}})
def get_document_chunks(doc_id: str, registry: RegistryDep) -> list[Chunk]:
    try:
        return registry.get_chunks(doc_id)
    except DocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.") from exc


@router.patch("/{doc_id}", responses={404: {"model": ErrorResponse}})
def rename_document(doc_id: str, body: RenameRequest, registry: RegistryDep) -> DocumentSummary:
    try:
        return registry.rename(doc_id, body.label.strip())
    except DocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.") from exc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": ErrorResponse}})
def delete_document(doc_id: str, registry: RegistryDep) -> Response:
    try:
        registry.delete(doc_id)
    except DocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
