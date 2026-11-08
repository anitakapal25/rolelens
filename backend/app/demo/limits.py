"""Public-demo protections: read-only documents and bounded chat spend.

Process-local and in-memory: right for a single free-tier instance; a shared store (Redis) would be
needed with several replicas.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import Settings

READ_ONLY_MESSAGE = ("This public demo is read-only and uses fictional sample documents. "
                     "Run RoleLens locally (see the README) to analyse your own resume.")


class RateLimiter:
    """Sliding one-hour window per client IP, plus a global cap per UTC day."""

    def __init__(self, per_ip_hour: int, daily_limit: int) -> None:
        self.per_ip_hour = per_ip_hour
        self.daily_limit = daily_limit
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._day = ""
        self._day_count = 0

    def check(self, client: str, now: float | None = None) -> str | None:
        """Record a request; return an error message if it is over a limit (and don't count it)."""
        now = time.time() if now is None else now
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        with self._lock:
            if day != self._day:
                self._day, self._day_count = day, 0
            if self._day_count >= self.daily_limit:
                return "The demo has reached today's question limit. Please try again tomorrow, or run RoleLens locally."
            hits = self._hits[client]
            while hits and hits[0] <= now - 3600:
                hits.popleft()
            if len(hits) >= self.per_ip_hour:
                wait = int(hits[0] + 3600 - now) // 60 + 1
                return f"Demo limit: {self.per_ip_hour} questions per hour. Try again in about {wait} min."
            hits.append(now)
            self._day_count += 1
            return None


def client_ip(request: Request) -> str:
    """Render (and most proxies) put the real client first in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_writable(settings: Settings) -> None:
    if settings.demo_mode:
        raise HTTPException(status.HTTP_403_FORBIDDEN, READ_ONLY_MESSAGE)


def enforce_chat_limit(limiter: RateLimiter | None, request: Request) -> None:
    if limiter is None:
        return
    message = limiter.check(client_ip(request))
    if message:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, message)
