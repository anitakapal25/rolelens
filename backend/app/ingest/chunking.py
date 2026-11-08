"""Section-aware chunking for resumes and job descriptions.

Pipeline: detect sections (header synonyms) -> split resume experience/projects into entries
-> split anything oversized on paragraph/bullet/line/sentence boundaries with a small overlap.
Every chunk carries doc + section (+ company/role/entry) metadata for filtering and citations.

All functions here are pure: text in, models out.
"""

import re

from pydantic import BaseModel

from app.models import Chunk, DocType

# Header synonyms -> canonical section name. Keys are normalized by _header_key().
RESUME_SECTIONS: dict[str, str] = {
    **dict.fromkeys(
        ["summary", "professional summary", "profile", "professional profile", "about me",
         "objective", "career objective", "career summary"], "summary"),
    **dict.fromkeys(
        ["skills", "technical skills", "core skills", "key skills", "skills and tools",
         "core competencies", "technologies", "tech stack", "technical expertise"], "skills"),
    **dict.fromkeys(
        ["experience", "professional experience", "work experience", "employment",
         "employment history", "work history", "career history", "relevant experience"], "experience"),
    **dict.fromkeys(
        ["projects", "ai projects", "personal projects", "selected projects", "key projects",
         "side projects", "academic projects"], "projects"),
    **dict.fromkeys(
        ["education", "academic background", "education and training", "qualifications"], "education"),
    **dict.fromkeys(
        ["certifications", "certificates", "licenses and certifications", "courses"], "certifications"),
    **dict.fromkeys(
        ["awards", "achievements", "honors", "honours", "awards and achievements"], "achievements"),
}

JOB_SECTIONS: dict[str, str] = {
    **dict.fromkeys(
        ["job description", "description", "role overview", "about the role", "overview", "the role",
         "position summary", "job summary", "role summary", "summary"], "overview"),
    **dict.fromkeys(
        ["responsibilities", "primary responsibilities", "key responsibilities",
         "roles and responsibilities", "role and responsibilities", "what you will do",
         "what you'll do", "duties", "your responsibilities", "what you'll be doing"], "responsibilities"),
    **dict.fromkeys(
        ["requirements", "required qualifications", "qualifications", "required skills",
         "minimum qualifications", "basic qualifications", "must have", "must haves",
         "skills", "what you bring", "what we're looking for", "who you are",
         "requirements and qualifications", "skills and qualifications"], "requirements"),
    **dict.fromkeys(
        ["preferred", "preferred qualifications", "preferred skills", "nice to have",
         "nice to haves", "bonus points", "good to have", "desired skills", "bonus"], "preferred"),
    **dict.fromkeys(["success measures", "what success looks like"], "success_measures"),
    **dict.fromkeys(["benefits", "what we offer", "perks", "compensation", "perks and benefits"], "benefits"),
    **dict.fromkeys(["about us", "about the company", "who we are", "company overview"], "about_company"),
}

SECTION_MAPS: dict[str, dict[str, str]] = {"resume": RESUME_SECTIONS, "job": JOB_SECTIONS}
PREAMBLE_SECTION: dict[str, str] = {"resume": "contact", "job": "overview"}
ENTRY_SECTIONS = {"experience", "projects"}

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:{_MONTH}\s+)?\d{{4}}"
DATE_RANGE = re.compile(rf"{_DATE}\s*(?:-|–|—|to)\s*(?:present|current|now|{_DATE})", re.IGNORECASE)
TITLE_SPLIT = re.compile(r"\s+\|\s+|\s+[–—]\s+|\s+@\s+|\s+at\s+")
ROLE_WORDS = re.compile(
    r"\b(engineer|developer|manager|lead|architect|analyst|intern|consultant|scientist|designer|"
    r"director|head|specialist|administrator|programmer|officer)\b",
    re.IGNORECASE,
)
CAPS_HEADER = re.compile(r"[A-Z][A-Z &/]{3,40}:?")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class Section(BaseModel):
    name: str
    text: str


class Entry(BaseModel):
    """A group of lines inside a section, e.g. one job in EXPERIENCE or one project."""

    text: str
    company: str | None = None
    role: str | None = None
    entry: str | None = None


# ---------- section detection ----------

def _header_key(line: str) -> str:
    key = line.strip().rstrip(":").strip().replace("&", "and")
    key = re.sub(r"[\s\-_]+", " ", key)
    return key.lower()


def match_header(line: str, doc_type: DocType) -> str | None:
    """Return the canonical section name if `line` is a section header, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > 60 or stripped.startswith("•"):
        return None
    key = _header_key(stripped)
    known = SECTION_MAPS[doc_type].get(key)
    if known:
        return known
    # Unknown ALL-CAPS short line (e.g. "VOLUNTEERING") is still a header.
    if CAPS_HEADER.fullmatch(stripped) and len(stripped.split()) <= 5:
        return key.replace(" ", "_")
    return None


def detect_sections(text: str, doc_type: DocType) -> list[Section]:
    """Split text into sections at header lines. Text before the first header is the preamble.

    Adjacent sections with the same canonical name are merged; header lines are dropped.
    """
    sections: list[Section] = []
    current_name = PREAMBLE_SECTION[doc_type]
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if not body:
            return
        if sections and sections[-1].name == current_name:
            sections[-1].text += "\n\n" + body
        else:
            sections.append(Section(name=current_name, text=body))

    for line in text.split("\n"):
        header = match_header(line, doc_type)
        if header:
            flush()
            buffer = []
            current_name = header
        else:
            buffer.append(line)
    flush()
    return sections


# ---------- entries inside experience / projects ----------

def parse_entry_header(line: str, next_line: str | None) -> tuple[str | None, str | None] | None:
    """Recognise an experience header such as 'Engineer | Acme' followed by a date range.

    Returns (role, company), or None if the line is not an entry header.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("•"):
        return None
    has_date = DATE_RANGE.search(stripped) is not None
    next_is_date = next_line is not None and DATE_RANGE.fullmatch(next_line.strip()) is not None
    if not (has_date or next_is_date):
        return None
    title = DATE_RANGE.sub("", stripped).strip(" |,–—-\t")
    parts = [p.strip() for p in TITLE_SPLIT.split(title) if p.strip()]
    if len(parts) < 2:
        return None
    first, second = parts[0], parts[1]
    if ROLE_WORDS.search(second) and not ROLE_WORDS.search(first):
        return second, first
    return first, second


def _is_project_title(line: str, next_line: str | None) -> bool:
    """A project title is a plain line followed by a 'Live demo | Python, ...' style line."""
    stripped = line.strip()
    if not stripped or stripped.startswith("•") or "|" in stripped or len(stripped) > 100:
        return False
    return next_line is not None and "|" in next_line and not next_line.strip().startswith("•")


def split_entries(section: Section) -> list[Entry]:
    """Split an experience or projects section into one Entry per job/project."""
    lines = section.text.split("\n")
    entries: list[Entry] = []
    current: list[str] = []
    meta: dict[str, str | None] = {"company": None, "role": None, "entry": None}

    def flush() -> None:
        body = "\n".join(current).strip()
        if body:
            entries.append(Entry(text=body, **meta))

    for i, line in enumerate(lines):
        next_line = lines[i + 1] if i + 1 < len(lines) else None
        new_meta: dict[str, str | None] | None = None
        if section.name == "experience":
            parsed = parse_entry_header(line, next_line)
            if parsed:
                role, company = parsed
                new_meta = {"company": company, "role": role, "entry": f"{role} | {company}"}
        elif _is_project_title(line, next_line):
            new_meta = {"company": None, "role": None, "entry": line.strip()}

        if new_meta is not None:
            flush()
            current = []
            meta = new_meta
        current.append(line)
    flush()
    return entries


# ---------- size control ----------

def _bullet_items(paragraph: str) -> list[str]:
    """Group lines into bullet items: a '• ' line plus its wrapped continuation lines."""
    items: list[list[str]] = []
    for line in paragraph.split("\n"):
        if line.startswith("• ") or not items:
            items.append([line])
        else:
            items[-1].append(line)
    return ["\n".join(item) for item in items]


def _units(text: str, max_chars: int) -> list[str]:
    """Break text into the largest natural units that each fit in max_chars.

    Order of preference: paragraphs -> bullet items -> lines -> sentences -> hard cut.
    """
    units: list[str] = []
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if len(para) <= max_chars:
            units.append(para)
            continue
        for item in _bullet_items(para):
            if len(item) <= max_chars:
                units.append(item)
                continue
            for line in item.split("\n"):
                if len(line) <= max_chars:
                    units.append(line)
                    continue
                for sentence in SENTENCE_END.split(line):
                    while len(sentence) > max_chars:
                        units.append(sentence[:max_chars])
                        sentence = sentence[max_chars:]
                    if sentence:
                        units.append(sentence)
    return units


def _tail(units: list[str], overlap_chars: int) -> list[str]:
    """The trailing units of a chunk whose combined length fits in overlap_chars."""
    tail: list[str] = []
    total = 0
    for unit in reversed(units):
        if total + len(unit) > overlap_chars:
            break
        tail.insert(0, unit)
        total += len(unit) + 1
    return tail


def split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Pack natural units into chunks of at most max_chars, repeating a small tail as overlap."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    chunks: list[str] = []
    current: list[str] = []
    for unit in _units(text, max_chars):
        candidate = "\n".join([*current, unit])
        if current and len(candidate) > max_chars:
            chunks.append("\n".join(current))
            current = _tail(current, overlap_chars)
            if len("\n".join([*current, unit])) > max_chars:
                current = []
        current.append(unit)
    if current:
        chunks.append("\n".join(current))
    return chunks


# ---------- public entry point ----------

def chunk_document(
    doc_id: str,
    doc_type: DocType,
    doc_label: str,
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 200,
) -> list[Chunk]:
    """Split a whole document into section-aware chunks with metadata."""
    chunks: list[Chunk] = []
    for section in detect_sections(text, doc_type):
        if doc_type == "resume" and section.name in ENTRY_SECTIONS:
            groups = split_entries(section)
        else:
            groups = [Entry(text=section.text)]
        for group in groups:
            for piece in split_text(group.text, max_chars, overlap_chars):
                index = len(chunks)
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc_id}:{index}",
                        doc_id=doc_id,
                        doc_type=doc_type,
                        doc_label=doc_label,
                        section=section.name,
                        index=index,
                        text=piece,
                        company=group.company,
                        role=group.role,
                        entry=group.entry,
                    )
                )
    return chunks
