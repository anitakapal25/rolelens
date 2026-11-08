"""Embeddings: OpenAI text-embedding-3-small, batched.

embedding_text() is pure: it prepends a short context header so a chunk like
"5+ years of Python" is embedded as "Job description · requirements" text, not as a bare line.
"""

import logging
from typing import Protocol

import openai

from app.llm.pricing import make_usage
from app.models import Chunk, Usage

logger = logging.getLogger(__name__)

DOC_KIND = {"resume": "Resume", "job": "Job description"}


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> tuple[list[list[float]], Usage]: ...


def embedding_text(chunk: Chunk) -> str:
    """Context header + chunk text. Uses section/entry (stable) rather than the user-editable label."""
    parts = [DOC_KIND[chunk.doc_type], chunk.section.replace("_", " ")]
    if chunk.entry:
        parts.append(chunk.entry)
    return f"[{' · '.join(parts)}]\n{chunk.text}"


def batched(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, batch_size: int = 100) -> None:
        self._client = openai.OpenAI(api_key=api_key, timeout=30.0, max_retries=2)
        self.model = model
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> tuple[list[list[float]], Usage]:
        vectors: list[list[float]] = []
        tokens = 0
        for batch in batched(texts, self.batch_size):
            try:
                response = self._client.embeddings.create(model=self.model, input=batch)
            except openai.AuthenticationError as exc:
                raise EmbeddingError("The OpenAI API key is missing or invalid.") from exc
            except openai.APIError as exc:
                raise EmbeddingError("The embedding service failed. Try again.") from exc
            # The API returns items with an index; sort to be safe before extending.
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
            tokens += response.usage.total_tokens
        usage = make_usage(self.model, tokens, 0)
        logger.info("embedded", extra={"texts": len(texts), "tokens": tokens, "cost_usd": usage.cost_usd})
        return vectors, usage
