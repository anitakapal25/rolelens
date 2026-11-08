"""Application settings, read from environment variables and the repo-root .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API keys (SecretStr keeps them out of logs and reprs)
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    # Models
    chat_model: str = "claude-sonnet-5-5"
    fast_model: str = "claude-haiku-5-5"
    embedding_model: str = "text-embedding-3-small"

    # Vector DB
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "rolelens_chunks"

    # Storage
    registry_db_path: Path = Path("./data/registry.sqlite3")

    # Upload limits
    max_upload_mb: int = 5
    max_pdf_pages: int = 10

    # Chunking
    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 200

    # Retrieval
    top_k_per_doc: int = 4

    # CORS (Vite dev server)
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
