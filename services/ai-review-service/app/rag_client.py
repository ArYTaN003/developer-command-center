"""Sync REST client to rag-context-service, wrapped in a circuit breaker.

If the RAG service is down, the breaker opens and the reviewer proceeds in
degraded mode (review without project context) rather than failing outright.
"""
import logging

import httpx
import pybreaker

from .config import settings

log = logging.getLogger("ai-review-service.rag")

rag_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.rag_breaker_fail_max,
    reset_timeout=settings.rag_breaker_reset_timeout,
    name="rag-context",
)


@rag_breaker
def _fetch(repo: str) -> str:
    url = f"{settings.rag_context_url}/context"
    resp = httpx.get(url, params={"repo": repo}, timeout=8.0)
    resp.raise_for_status()
    return resp.json().get("summary", "")


def get_context(repo: str) -> tuple[str, bool]:
    """Return (context_summary, degraded?)."""
    try:
        return _fetch(repo), False
    except Exception as exc:
        log.warning("RAG context unavailable for %s: %s", repo, exc)
        return "", True
