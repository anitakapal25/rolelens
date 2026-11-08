"""Chat use case: route -> retrieve -> build prompt -> stream a grounded answer.

Routing and retrieval run eagerly (before the HTTP stream starts) so their failures become normal
HTTP errors; only the model's answer is streamed.
"""

import logging
import re
import time
from collections.abc import Iterator
from typing import Any

from app.ingest.registry import DocumentRegistry
from app.llm.client import LLMError, StreamDone, TextDelta
from app.llm.prompts import build_answer_prompt
from app.models import RetrievalResponse, RetrievedChunk
from app.retrieval.router import DocRef, route_question
from app.retrieval.search import retrieve
from app.services import Services

logger = logging.getLogger(__name__)

CITATION = re.compile(r"\[(\d{1,3})\]")


def load_doc_refs(registry: DocumentRegistry) -> list[DocRef]:
    refs = []
    for doc in registry.list_summaries():
        _, extraction = registry.get_extraction(doc.doc_id)
        extraction = extraction or {}
        refs.append(DocRef(
            doc_id=doc.doc_id, doc_type=doc.doc_type, label=doc.label, job_number=doc.job_number,
            title=extraction.get("title"), company=extraction.get("company"),
        ))
    return refs


def doc_order_key(refs: list[DocRef]) -> Any:
    """Resume first, then jobs by number."""
    order = {r.doc_id: (0 if r.doc_type == "resume" else 1, r.job_number or 0) for r in refs}
    return lambda doc_id: order.get(doc_id, (2, 0))


def extract_citations(text: str, max_n: int) -> list[int]:
    """Pure: the distinct valid [n] citations in an answer, in first-seen order."""
    seen: list[int] = []
    for m in CITATION.findall(text):
        n = int(m)
        if 1 <= n <= max_n and n not in seen:
            seen.append(n)
    return seen


def retrieve_for_question(svc: Services, question: str) -> RetrievalResponse:
    s = svc.settings
    refs = load_doc_refs(svc.registry)
    route = route_question(question, refs, svc.llm, s.fast_model)
    resume_ids = {r.doc_id for r in refs if r.doc_type == "resume"}

    def k_for(doc_id: str) -> int:
        return s.top_k_resume if doc_id in resume_ids else s.top_k_per_doc

    sources = retrieve(question, route.doc_ids, svc.embedder, svc.store, k_for, s.max_distance,
                       doc_order_key(refs))
    # The registry owns labels; the index may hold a stale one after a rename.
    labels = {r.doc_id: r.label for r in refs}
    sources = [
        RetrievedChunk(n=r.n, distance=r.distance,
                       chunk=r.chunk.model_copy(update={"doc_label": labels.get(r.chunk.doc_id, r.chunk.doc_label)}))
        for r in sources
    ]
    logger.info("retrieved", extra={
        "route_method": route.method, "routed_doc_ids": route.doc_ids,
        "chunks": [(r.chunk.chunk_id, r.distance) for r in sources],
    })
    return RetrievalResponse(route=route, sources=sources)


def stream_answer(svc: Services, question: str, retrieval: RetrievalResponse) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (event, data) pairs: token... then done (or error)."""
    s = svc.settings
    started = time.perf_counter()
    labels = [r.label for r in load_doc_refs(svc.registry)]
    system, messages = build_answer_prompt(question, retrieval.sources, labels)
    answer_parts: list[str] = []
    try:
        for event in svc.llm.stream_text(model=s.chat_model, system=system, messages=messages,  # type: ignore[arg-type]
                                         effort=s.chat_effort, max_tokens=s.chat_max_tokens):
            if isinstance(event, TextDelta):
                answer_parts.append(event.text)
                yield "token", {"text": event.text}
            elif isinstance(event, StreamDone):
                answer = "".join(answer_parts)
                done = {
                    "citations": extract_citations(answer, len(retrieval.sources)),
                    "stop_reason": event.stop_reason,
                    "usage": event.usage.model_dump(),
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                }
                logger.info("answered", extra={"question": question, **done})
                yield "done", done
    except LLMError as exc:
        logger.error("answer stream failed", extra={"error": str(exc)})
        yield "error", {"detail": str(exc), "retryable": exc.retryable}
