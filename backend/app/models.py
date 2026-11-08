"""Pydantic models shared across layers (HTTP bodies, registry records, chunks)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["resume", "job"]


class Chunk(BaseModel):
    """One retrievable piece of a document, with the metadata needed to filter and cite it."""

    chunk_id: str
    doc_id: str
    doc_type: DocType
    doc_label: str
    section: str
    index: int
    text: str
    company: str | None = None
    role: str | None = None
    entry: str | None = None


class SectionSummary(BaseModel):
    name: str
    chunk_count: int


class DocumentSummary(BaseModel):
    doc_id: str
    doc_type: DocType
    label: str
    filename: str
    job_number: int | None = None
    page_count: int
    char_count: int
    chunk_count: int
    sections: list[SectionSummary]
    created_at: datetime


class RenameRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)


class ErrorResponse(BaseModel):
    detail: str
