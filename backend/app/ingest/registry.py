"""SQLite document registry: the source of truth for documents and their chunks.

Chroma (added in M4) is a derived search index that can be rebuilt from this registry.
Uses the stdlib sqlite3 module; one short-lived connection per operation.
"""

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models import Chunk, DocType, DocumentSummary, SectionSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id          TEXT PRIMARY KEY,
    doc_type        TEXT NOT NULL CHECK (doc_type IN ('resume', 'job')),
    label           TEXT NOT NULL,
    label_is_custom INTEGER NOT NULL DEFAULT 0,
    job_number      INTEGER,
    filename        TEXT NOT NULL,
    page_count      INTEGER NOT NULL,
    char_count      INTEGER NOT NULL,
    raw_text        TEXT NOT NULL,
    extraction_json TEXT,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id   TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    idx      INTEGER NOT NULL,
    section  TEXT NOT NULL,
    company  TEXT,
    role     TEXT,
    entry    TEXT,
    text     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
"""


class DocumentNotFound(Exception):
    pass


class DocumentRegistry:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ----- writes -----

    def add_document(
        self,
        doc_id: str,
        doc_type: DocType,
        label: str,
        label_is_custom: bool,
        job_number: int | None,
        filename: str,
        page_count: int,
        raw_text: str,
        chunks: list[Chunk],
        extraction: dict[str, Any] | None = None,
    ) -> DocumentSummary:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO documents (doc_id, doc_type, label, label_is_custom, job_number, filename,"
                " page_count, char_count, raw_text, extraction_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, doc_type, label, int(label_is_custom), job_number, filename, page_count,
                 len(raw_text), raw_text, json.dumps(extraction) if extraction is not None else None,
                 datetime.now(UTC).isoformat()),
            )
            conn.executemany(
                "INSERT INTO chunks (chunk_id, doc_id, idx, section, company, role, entry, text)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(c.chunk_id, c.doc_id, c.index, c.section, c.company, c.role, c.entry, c.text)
                 for c in chunks],
            )
        return self.get_summary(doc_id)

    def rename(self, doc_id: str, label: str) -> DocumentSummary:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE documents SET label = ?, label_is_custom = 1 WHERE doc_id = ?", (label, doc_id)
            )
            if cur.rowcount == 0:
                raise DocumentNotFound(doc_id)
        return self.get_summary(doc_id)

    def delete(self, doc_id: str) -> None:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            if cur.rowcount == 0:
                raise DocumentNotFound(doc_id)

    def get_extraction(self, doc_id: str) -> tuple[DocType, dict[str, Any] | None]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT doc_type, extraction_json FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        if row is None:
            raise DocumentNotFound(doc_id)
        data = json.loads(row["extraction_json"]) if row["extraction_json"] else None
        return row["doc_type"], data

    # ----- reads -----

    def next_job_number(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(job_number), 0) FROM documents").fetchone()
        return int(row[0]) + 1

    def resume_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT doc_id FROM documents WHERE doc_type = 'resume'").fetchall()
        return [r["doc_id"] for r in rows]

    def list_summaries(self) -> list[DocumentSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT doc_id FROM documents ORDER BY doc_type DESC, job_number, created_at"
            ).fetchall()
        return [self.get_summary(r["doc_id"]) for r in rows]

    def get_summary(self, doc_id: str) -> DocumentSummary:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT doc_id, doc_type, label, filename, job_number, page_count, char_count, created_at"
                " FROM documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                raise DocumentNotFound(doc_id)
            sections = conn.execute(
                "SELECT section FROM chunks WHERE doc_id = ? ORDER BY idx", (doc_id,)
            ).fetchall()
        counts = Counter(s["section"] for s in sections)  # Counter keeps first-seen order
        return DocumentSummary(
            **dict(row),
            chunk_count=len(sections),
            sections=[SectionSummary(name=n, chunk_count=c) for n, c in counts.items()],
        )

    def get_chunks(self, doc_id: str) -> list[Chunk]:
        with self._connect() as conn:
            doc = conn.execute(
                "SELECT doc_type, label FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            if doc is None:
                raise DocumentNotFound(doc_id)
            rows = conn.execute(
                "SELECT * FROM chunks WHERE doc_id = ? ORDER BY idx", (doc_id,)
            ).fetchall()
        return [
            Chunk(
                chunk_id=r["chunk_id"], doc_id=doc_id, doc_type=doc["doc_type"], doc_label=doc["label"],
                section=r["section"], index=r["idx"], text=r["text"],
                company=r["company"], role=r["role"], entry=r["entry"],
            )
            for r in rows
        ]
