from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import build_services, create_app
from app.services import Services
from tests.fakes import FakeEmbedder, FakeLLM, InMemoryStore

RESUME_TEXT = """Jane Doe
Backend Engineer | jane@example.com
PROFESSIONAL SUMMARY
Engineer with 6 years building APIs.
Technical Skills
Python, FastAPI, PostgreSQL, Docker
AI PROJECTS
DocBot - Retrieval Assistant
Live demo | Python, ChromaDB
• Built a retrieval assistant over PDFs.
Professional Experience
Senior Engineer | Acme Corp
Jan 2021 - Present
• Led the payments API rewrite.
• Cut p95 latency by 40%.
Software Developer | Globex
Mar 2018 - Dec 2020
• Built reporting dashboards.
Education
BSc Computer Science | State University
2014 - 2018
"""

JOB_TEXT = """Senior Backend Engineer - Initech
About the role
You will own our ingestion platform.
Key Responsibilities:
Design APIs.
Run on-call.
Requirements
5+ years of Python.
Experience with Kafka.
Nice to have
Rust.
"""


@pytest.fixture
def resume_text() -> str:
    return RESUME_TEXT


@pytest.fixture
def job_text() -> str:
    return JOB_TEXT


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(registry_db_path=tmp_path / "registry.sqlite3", max_upload_mb=1, _env_file=None)


@pytest.fixture
def services(settings: Settings) -> Services:
    return build_services(settings, llm=FakeLLM(), embedder=FakeEmbedder(), store=InMemoryStore())


@pytest.fixture
def client(settings: Settings, services: Services) -> TestClient:
    return TestClient(create_app(settings, services))
