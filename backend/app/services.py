"""The bundle of long-lived dependencies the API hands to service functions."""

from dataclasses import dataclass

from app.config import Settings
from app.demo.limits import RateLimiter
from app.ingest.registry import DocumentRegistry
from app.llm.client import LLMClient
from app.retrieval.embed import Embedder
from app.retrieval.store import VectorStore


@dataclass
class Services:
    settings: Settings
    registry: DocumentRegistry
    llm: LLMClient
    embedder: Embedder
    store: VectorStore
    limiter: RateLimiter | None = None         # chat; set in demo mode or with RATE_LIMIT=true
    upload_limiter: RateLimiter | None = None  # uploads; same switch
