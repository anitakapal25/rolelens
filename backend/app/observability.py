"""Structured JSON logs with a request id on every line, plus a small in-memory metrics store.

- RequestContextMiddleware: assigns/propagates X-Request-ID, times each request, records metrics.
- JsonFormatter: one JSON object per line; includes `extra={...}` fields and the current request id.
- Metrics: thread-safe counters/latencies for GET /metrics (resets on restart; Prometheus/OTel is
  the production answer, see README).
"""

import contextvars
import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "openai", "anthropic", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class Metrics:
    """Process-local counters. Good enough for one container; not shared across replicas."""

    def __init__(self, window: int = 500) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self.requests: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self.latency_ms: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self.llm_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0
        self.chat_answers = 0
        self.chat_errors = 0
        self.retrieval_ms: deque[float] = deque(maxlen=window)

    def record_request(self, route: str, status: int, ms: float) -> None:
        with self._lock:
            self.requests[route] += 1
            self.latency_ms[route].append(ms)
            if status >= 500:
                self.errors[route] += 1

    def record_usage(self, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        with self._lock:
            self.llm_calls += 1
            self.tokens_in += input_tokens
            self.tokens_out += output_tokens
            self.cost_usd += cost_usd

    def record_chat(self, ok: bool, retrieval_ms: float) -> None:
        with self._lock:
            self.retrieval_ms.append(retrieval_ms)
            if ok:
                self.chat_answers += 1
            else:
                self.chat_errors += 1

    def snapshot(self) -> dict[str, Any]:
        def pct(values: list[float], q: float) -> float | None:
            if not values:
                return None
            ordered = sorted(values)
            return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 1)

        with self._lock:
            routes = {
                route: {"count": n, "errors_5xx": self.errors.get(route, 0),
                        "p50_ms": pct(list(self.latency_ms[route]), 0.5),
                        "p95_ms": pct(list(self.latency_ms[route]), 0.95)}
                for route, n in sorted(self.requests.items())
            }
            return {
                "uptime_s": round(time.time() - self.started),
                "routes": routes,
                "chat": {"answers": self.chat_answers, "errors": self.chat_errors,
                         "retrieval_p50_ms": pct(list(self.retrieval_ms), 0.5),
                         "retrieval_p95_ms": pct(list(self.retrieval_ms), 0.95)},
                "llm": {"calls": self.llm_calls, "input_tokens": self.tokens_in,
                        "output_tokens": self.tokens_out, "estimated_cost_usd": round(self.cost_usd, 4)},
            }


metrics = Metrics()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            ms = (time.perf_counter() - started) * 1000
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            key = f"{request.method} {path}"
            metrics.record_request(key, status, ms)
            logging.getLogger("app.http").info(
                "request", extra={"method": request.method, "path": path, "status": status, "ms": round(ms, 1)})
            request_id_var.reset(token)
