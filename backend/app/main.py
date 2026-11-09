"""FastAPI application factory."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, documents, fit
from app.config import Settings, get_settings
from app.ingest.parse import EmptyDocument, FileTooLarge, IngestError, TooManyPages, UnsupportedFileType
from app.ingest.registry import DocumentRegistry
from app.llm.client import ClaudeClient, LLMClient, LLMError
from app.observability import RequestContextMiddleware, configure_logging, metrics
from app.retrieval.embed import Embedder, EmbeddingError, OpenAIEmbedder
from app.retrieval.store import ChromaStore, MemoryStore, VectorStore, VectorStoreError
from app.demo.limits import build_limiters
from app.services import Services

logger = logging.getLogger(__name__)

INGEST_ERROR_STATUS: dict[type[IngestError], int] = {
    UnsupportedFileType: 400,
    FileTooLarge: 413,
    TooManyPages: 422,
    EmptyDocument: 422,
}


def build_services(
    settings: Settings,
    llm: LLMClient | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> Services:
    """Real clients by default; tests pass fakes."""
    return Services(
        settings=settings,
        registry=DocumentRegistry(settings.registry_db_path),
        llm=llm or ClaudeClient(settings.anthropic_api_key.get_secret_value()),
        embedder=embedder or OpenAIEmbedder(settings.openai_api_key.get_secret_value(), settings.embedding_model),
        store=store or (MemoryStore() if settings.vector_store == "memory"
                        else ChromaStore(settings.chroma_host, settings.chroma_port, settings.chroma_collection)),
    )


def _start_demo(svc: Services) -> None:
    """Public demo: load the pre-built sample seed (no model calls)."""
    from app.demo.seed import read_seed, load_seed

    loaded = load_seed(svc, read_seed())
    logger.info("demo mode", extra={"seeded_documents": loaded, "vector_store": svc.settings.vector_store})


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    app = FastAPI(title="RoleLens API", version="0.1.0")
    app.state.services = services or build_services(settings)
    app.state.services.limiter, app.state.services.upload_limiter = build_limiters(settings)
    if settings.demo_mode:
        _start_demo(app.state.services)

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.exception_handler(IngestError)
    async def ingest_error_handler(_: Request, exc: IngestError) -> JSONResponse:
        code = INGEST_ERROR_STATUS.get(type(exc), 400)
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    @app.exception_handler(LLMError)
    async def llm_error_handler(_: Request, exc: LLMError) -> JSONResponse:
        logger.error("llm error", extra={"error": str(exc), "retryable": exc.retryable})
        return JSONResponse(status_code=503 if exc.retryable else 502, content={"detail": str(exc)})

    @app.exception_handler(EmbeddingError)
    async def embedding_error_handler(_: Request, exc: EmbeddingError) -> JSONResponse:
        logger.error("embedding error", extra={"error": str(exc)})
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(VectorStoreError)
    async def store_error_handler(_: Request, exc: VectorStoreError) -> JSONResponse:
        logger.error("vector store error", extra={"error": str(exc)})
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/health")
    def health() -> dict[str, object]:
        """Liveness plus dependency checks. 'degraded' = API up but the vector DB is unreachable."""
        svc: Services = app.state.services
        try:
            indexed: int | str = svc.store.count()
            chroma = "ok"
        except VectorStoreError:
            indexed, chroma = "unknown", "unavailable"
        return {
            "status": "ok" if chroma == "ok" else "degraded",
            "chroma": chroma,
            "documents": svc.registry.count(),
            "indexed_chunks": indexed,
        }

    @app.get("/config")
    def get_config() -> dict[str, object]:
        """What the frontend needs to adapt its UI (e.g. hide uploads in the public demo)."""
        return {"demo": settings.demo_mode, "demo_rate_per_ip_hour": settings.demo_rate_per_ip_hour}

    @app.get("/metrics")
    def get_metrics() -> dict[str, object]:
        return metrics.snapshot()

    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(fit.router)
    return app


app = create_app()
