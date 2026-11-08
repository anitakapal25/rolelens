"""The bundle of long-lived dependencies the API hands to service functions."""

from dataclasses import dataclass

from app.config import Settings
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
