"""Demo seed: a snapshot of fully processed sample documents (chunks, extractions, embeddings and
fit matches), so the free-tier demo starts with zero model calls.

    python -m app.demo.seed build    # run once locally with real keys; writes app/demo/seed.json
    load_seed(services)              # called at startup when DEMO_MODE=true

Only the fictional sample documents in app/eval/sample_docs are ever exported.
"""

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.config import get_settings
from app.fit.service import fit_for_all
from app.ingest.service import ingest_document
from app.models import Chunk
from app.retrieval.embed import embedding_text
from app.services import Services

SEED_PATH = Path(__file__).parent / "seed.json"
SAMPLE_DIR = Path(__file__).parents[1] / "eval" / "sample_docs"
SAMPLES = [("resume_jordan_rivera.txt", "resume"), ("job1_meridian_health.txt", "job"),
           ("job2_lumen_labs.txt", "job"), ("job3_brightwave.txt", "job")]


class SeedDocument(BaseModel):
    doc_id: str
    doc_type: str
    label: str
    job_number: int | None
    filename: str
    page_count: int
    raw_text: str
    extraction: dict[str, Any] | None
    warnings: list[str]
    chunks: list[Chunk]
    vectors: list[list[float]]


class Seed(BaseModel):
    embedding_model: str
    documents: list[SeedDocument]
    fit_cache: list[dict[str, Any]]


def export_seed(svc: Services) -> Seed:
    """Read everything back out of a populated registry + store."""
    docs = []
    for summary in svc.registry.list_summaries():
        chunks = svc.registry.get_chunks(summary.doc_id)
        vectors, _ = svc.embedder.embed([embedding_text(c) for c in chunks])  # same text the index holds
        _, extraction = svc.registry.get_extraction(summary.doc_id)
        docs.append(SeedDocument(
            doc_id=summary.doc_id, doc_type=summary.doc_type, label=summary.label, job_number=summary.job_number,
            filename=summary.filename, page_count=summary.page_count, raw_text=svc.registry.get_raw_text(summary.doc_id),
            extraction=extraction, warnings=summary.warnings, chunks=chunks, vectors=vectors,
        ))
    resume_id = next(d.doc_id for d in docs if d.doc_type == "resume")
    fit_cache = [{"job_id": d.doc_id, "resume_id": resume_id, "matches": svc.registry.get_fit_matches(d.doc_id, resume_id)}
                 for d in docs if d.doc_type == "job"]
    return Seed(embedding_model=svc.settings.embedding_model, documents=docs, fit_cache=fit_cache)


def load_seed(svc: Services, seed: Seed) -> int:
    """Fill an empty registry and an empty vector store from a seed. Each is checked separately:
    the in-memory store is per process, while the SQLite registry may already hold the seed
    (e.g. a second app instance in the same process). Returns the number of documents inserted."""
    inserted = 0
    if svc.registry.count() == 0:
        for d in seed.documents:
            svc.registry.add_document(
                doc_id=d.doc_id, doc_type=d.doc_type, label=d.label, label_is_custom=False,  # type: ignore[arg-type]
                job_number=d.job_number, filename=d.filename, page_count=d.page_count, raw_text=d.raw_text,
                chunks=d.chunks, extraction=d.extraction, warnings=d.warnings,
            )
            inserted += 1
        svc.registry.sync_job_counter()
        for entry in seed.fit_cache:
            if entry["matches"] is not None:
                svc.registry.set_fit_matches(entry["job_id"], entry["resume_id"], entry["matches"])
    if svc.store.count() == 0:
        for d in seed.documents:
            svc.store.upsert(d.chunks, d.vectors)
    return inserted


def read_seed(path: Path = SEED_PATH) -> Seed:
    return Seed.model_validate_json(path.read_text())


def build(path: Path = SEED_PATH) -> None:
    """Ingest the sample documents with real models, compute fit matches, write the snapshot."""
    from app.main import build_services
    from app.retrieval.store import MemoryStore

    with tempfile.TemporaryDirectory() as tmp:
        settings = get_settings().model_copy(update={"registry_db_path": Path(tmp) / "seed.sqlite3"})
        svc = build_services(settings, store=MemoryStore())
        for filename, doc_type in SAMPLES:
            doc = ingest_document(svc, filename, (SAMPLE_DIR / filename).read_bytes(), doc_type)  # type: ignore[arg-type]
            print(f"  {doc.label}  ({doc.chunk_count} chunks)")
        for report in fit_for_all(svc):
            print(f"  fit {report.job_label[:40]:40} {report.score}")
        seed = export_seed(svc)
    path.write_text(json.dumps(seed.model_dump(mode="json"), separators=(",", ":")))
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if sys.argv[1:] != ["build"]:
        sys.exit("usage: python -m app.demo.seed build")
    build()
