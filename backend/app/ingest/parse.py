"""Turn uploaded bytes (PDF, DOCX, TXT) into clean plain text.

Validation errors are raised as IngestError subclasses; the API layer maps them to HTTP codes.
"""

import io
import re
from pathlib import Path

import docx
import pymupdf
from pydantic import BaseModel

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
BULLET_GLYPHS = "•●▪◦‣∙·"


class IngestError(Exception):
    """Base class for upload problems the user can fix."""


class UnsupportedFileType(IngestError):
    pass


class FileTooLarge(IngestError):
    pass


class TooManyPages(IngestError):
    pass


class EmptyDocument(IngestError):
    pass


class ParsedDocument(BaseModel):
    text: str
    page_count: int


def parse_document(filename: str, data: bytes, max_bytes: int, max_pages: int) -> ParsedDocument:
    """Validate the upload and extract normalized text."""
    if len(data) > max_bytes:
        raise FileTooLarge(f"File is larger than {max_bytes // (1024 * 1024)} MB.")

    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileType(f"Unsupported file type '{ext or 'none'}'. Use PDF, DOCX or TXT.")

    if ext == ".pdf":
        raw, pages = _parse_pdf(data, max_pages)
    elif ext == ".docx":
        raw, pages = _parse_docx(data), 1
    else:
        raw, pages = _parse_txt(data), 1

    text = normalize_text(raw)
    if not text:
        raise EmptyDocument("No text found. If this is a scanned PDF, upload a text-based version.")
    return ParsedDocument(text=text, page_count=pages)


def _parse_pdf(data: bytes, max_pages: int) -> tuple[str, int]:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise UnsupportedFileType("Could not read this PDF. Is the file corrupted?") from exc
    with doc:
        if doc.page_count > max_pages:
            raise TooManyPages(f"PDF has {doc.page_count} pages; the limit is {max_pages}.")
        text = "\n".join(page.get_text() for page in doc)
        return text, doc.page_count


def _parse_docx(data: bytes) -> str:
    try:
        document = docx.Document(io.BytesIO(data))
    except (ValueError, KeyError, OSError) as exc:
        raise UnsupportedFileType("Could not read this DOCX file.") from exc
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(lines)


def _parse_txt(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def normalize_text(raw: str) -> str:
    """Normalize whitespace and bullets so section detection sees consistent lines.

    - PDF extractors often emit a bullet glyph on its own line: join it with the next line.
    - Every bullet becomes "• ".
    - Runs of blank lines collapse to one.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = text.replace("’", "'")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(rf"^ *[{BULLET_GLYPHS}] *\n *", "• ", text, flags=re.MULTILINE)
    text = re.sub(rf"^ *[{BULLET_GLYPHS}] *", "• ", text, flags=re.MULTILINE)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
