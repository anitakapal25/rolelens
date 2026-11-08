"""Chat routes: SSE answer stream, plus a retrieval-only endpoint for debugging and eval."""

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import ServicesDep
from app.chat.service import retrieve_for_question, stream_answer
from app.models import ChatRequest, ErrorResponse, RetrievalResponse

router = APIRouter(prefix="/chat", tags=["chat"])

UPSTREAM = {502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


def to_sse(events: Iterator[tuple[str, dict[str, Any]]]) -> Iterator[str]:
    for event, data in events:
        yield f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("", responses=UPSTREAM)
def chat(body: ChatRequest, svc: ServicesDep) -> StreamingResponse:
    """Server-Sent Events: route, sources, token*, then done | error."""
    retrieval = retrieve_for_question(svc, body.question)  # errors here -> normal HTTP error codes

    def events() -> Iterator[tuple[str, dict[str, Any]]]:
        yield "route", retrieval.route.model_dump()
        yield "sources", {"sources": [s.model_dump() for s in retrieval.sources]}
        yield from stream_answer(svc, body.question, retrieval)

    return StreamingResponse(
        to_sse(events()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/retrieve", responses=UPSTREAM)
def chat_retrieve(body: ChatRequest, svc: ServicesDep) -> RetrievalResponse:
    """Routing + retrieval only, no answer. Used to check routing with curl and by the eval runner."""
    return retrieve_for_question(svc, body.question)
