from app.ingest.chunking import (
    Section,
    chunk_document,
    detect_sections,
    match_header,
    parse_entry_header,
    split_entries,
    split_text,
)
from app.ingest.parse import normalize_text


# ----- header matching -----

def test_header_synonyms_map_to_canonical_names() -> None:
    assert match_header("Professional Experience", "resume") == "experience"
    assert match_header("AI PROJECTS", "resume") == "projects"
    assert match_header("Technical Skills", "resume") == "skills"
    assert match_header("Roles & Responsibilities", "job") == "responsibilities"
    assert match_header("Required Qualifications:", "job") == "requirements"
    assert match_header("Nice-to-have", "job") == "preferred"


def test_same_word_means_different_sections_per_doc_type() -> None:
    assert match_header("Skills", "resume") == "skills"
    assert match_header("Skills", "job") == "requirements"


def test_content_lines_are_not_headers() -> None:
    assert match_header("• Experience with Kafka.", "job") is None
    assert match_header("5+ years of Python.", "job") is None
    assert match_header("Python, FastAPI, PostgreSQL", "resume") is None


def test_unknown_all_caps_line_is_a_header() -> None:
    assert match_header("VOLUNTEERING", "resume") == "volunteering"


# ----- section detection -----

def test_resume_sections_detected_in_order(resume_text: str) -> None:
    names = [s.name for s in detect_sections(resume_text, "resume")]
    assert names == ["contact", "summary", "skills", "projects", "experience", "education"]


def test_job_sections_detected_with_preamble_as_overview(job_text: str) -> None:
    sections = detect_sections(job_text, "job")
    assert [s.name for s in sections] == ["overview", "responsibilities", "requirements", "preferred"]
    # Preamble and "About the role" are both overview, so they merge into one section.
    assert "Initech" in sections[0].text and "ingestion platform" in sections[0].text


def test_header_lines_are_not_kept_in_section_text(job_text: str) -> None:
    for section in detect_sections(job_text, "job"):
        assert "Key Responsibilities" not in section.text


# ----- experience / project entries -----

def test_entry_header_extracts_role_and_company() -> None:
    assert parse_entry_header("Senior Engineer | Acme Corp", "Jan 2021 - Present") == ("Senior Engineer", "Acme Corp")
    assert parse_entry_header("Acme Corp — Staff Engineer  2019 - 2021", None) == ("Staff Engineer", "Acme Corp")
    assert parse_entry_header("Live demo | Python, ChromaDB", "• Built it") is None
    assert parse_entry_header("• Led migration 2019 - 2020 | Acme", None) is None


def test_experience_split_into_one_entry_per_job(resume_text: str) -> None:
    experience = next(s for s in detect_sections(resume_text, "resume") if s.name == "experience")
    entries = split_entries(experience)
    assert [(e.role, e.company) for e in entries] == [
        ("Senior Engineer", "Acme Corp"),
        ("Software Developer", "Globex"),
    ]
    assert "payments API" in entries[0].text and "payments API" not in entries[1].text


def test_projects_split_by_title_line() -> None:
    section = Section(
        name="projects",
        text="Alpha - Tool\nLive demo | Python\n• Did A.\nBeta\nRepo | Go\n• Did B.",
    )
    assert [e.entry for e in split_entries(section)] == ["Alpha - Tool", "Beta"]


# ----- size control -----

def test_short_text_is_one_chunk() -> None:
    assert split_text("short", max_chars=100, overlap_chars=20) == ["short"]


def test_oversized_text_respects_max_and_overlaps() -> None:
    lines = [f"• Bullet number {i} describing some work." for i in range(30)]
    chunks = split_text("\n".join(lines), max_chars=300, overlap_chars=80)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    # The tail of each chunk (one or more whole bullets, <= overlap_chars) opens the next one.
    for prev, nxt in zip(chunks, chunks[1:]):
        prev_lines, next_lines = prev.split("\n"), nxt.split("\n")
        shared = [line for line in next_lines if line in prev_lines]
        assert shared, "expected overlap"
        assert next_lines[: len(shared)] == prev_lines[-len(shared):]
        assert len("\n".join(shared)) <= 80


def test_bullet_items_are_not_split_mid_item() -> None:
    items = [f"• Item {i} first line\ncontinued wrapped line {i}" for i in range(20)]
    for chunk in split_text("\n".join(items), max_chars=200, overlap_chars=0):
        assert chunk.startswith("• Item")


def test_single_huge_line_is_hard_cut() -> None:
    chunks = split_text("x" * 2500, max_chars=1000, overlap_chars=0)
    assert [len(c) for c in chunks] == [1000, 1000, 500]


# ----- end to end -----

def test_chunk_document_attaches_metadata(resume_text: str) -> None:
    chunks = chunk_document("doc1", "resume", "Resume", resume_text)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(c.chunk_id == f"doc1:{c.index}" for c in chunks)
    assert all(c.doc_type == "resume" and c.doc_label == "Resume" for c in chunks)
    acme = [c for c in chunks if c.company == "Acme Corp"]
    assert len(acme) == 1 and acme[0].section == "experience" and acme[0].role == "Senior Engineer"


def test_pdf_style_bullets_normalized_before_chunking() -> None:
    raw = "Experience\nEngineer | Acme\n2020 - 2022\n•\nShipped things\n●  Fixed things"
    text = normalize_text(raw)
    assert "• Shipped things" in text and "• Fixed things" in text
    chunks = chunk_document("d", "resume", "Resume", text)
    assert chunks[0].company == "Acme"
