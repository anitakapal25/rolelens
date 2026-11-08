"""Chat routes: SSE answer stream, plus a retrieval-only endpoint for debugging and eval."""

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import ServicesDep
from app.chat.service import retrieve_for_question, stream_answer
from app.demo.limits import enforce_chat_limit
from app.models import ChatRequest, ErrorResponse, RetrievalResponse
from app.observability import request_id_var

router = APIRouter(prefix="/chat", tags=["chat"])

UPSTREAM = {429: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


def to_sse(events: Iterator[tuple[str, dict[str, Any]]]) -> Iterator[str]:
    for event, data in events:
        yield f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("", responses=UPSTREAM)
def chat(body: ChatRequest, svc: ServicesDep, request: Request) -> StreamingResponse:
    """Server-Sent Events: route, sources, token*, then done | error."""
    enforce_chat_limit(svc.limiter, request)  # no-op outside demo mode
    retrieval = retrieve_for_question(svc, body.question)  # errors here -> normal HTTP error codes
    request_id = request_id_var.get()  # the stream outlives the middleware's context

    def events() -> Iterator[tuple[str, dict[str, Any]]]:
        request_id_var.set(request_id)
        yield "route", retrieval.route.model_dump()
        yield "sources", {"sources": [s.model_dump() for s in retrieval.sources]}
        yield from stream_answer(svc, body.question, retrieval)

    return StreamingResponse(
        to_sse(events()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/retrieve", responses=UPSTREAM)
def chat_retrieve(body: ChatRequest, svc: ServicesDep, request: Request) -> RetrievalResponse:
    """Routing + retrieval only, no answer. Used to check routing with curl and by the eval runner."""
    enforce_chat_limit(svc.limiter, request)
    return retrieve_for_question(svc, body.question)
