import pytest

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
