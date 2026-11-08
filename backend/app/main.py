"""FastAPI application factory."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import documents
from app.config import Settings, get_settings
from app.ingest.parse import EmptyDocument, FileTooLarge, IngestError, TooManyPages, UnsupportedFileType
from app.ingest.registry import DocumentRegistry

INGEST_ERROR_STATUS: dict[type[IngestError], int] = {
    UnsupportedFileType: 400,
    FileTooLarge: 413,
    TooManyPages: 422,
    EmptyDocument: 422,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO)

    app = FastAPI(title="RoleLens API", version="0.1.0")
    app.state.registry = DocumentRegistry(settings.registry_db_path)
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(IngestError)
    async def ingest_error_handler(_: Request, exc: IngestError) -> JSONResponse:
        code = INGEST_ERROR_STATUS.get(type(exc), 400)
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(documents.router)
    return app


app = create_app()
