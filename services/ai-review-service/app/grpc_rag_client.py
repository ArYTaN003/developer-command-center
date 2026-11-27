"""gRPC client to rag-context-service (Lab 3B: synchronous gRPC).

Drop-in replacement for rag_client.get_context: same signature
`get_context(repo) -> (summary, degraded?)`, but the project-context lookup now
travels over gRPC instead of REST. Wrapped in the SAME circuit breaker
(`rag_breaker`) so degraded-mode behaviour is identical when RAG is down.

The REST client in rag_client.py is kept intentionally for the REST-vs-gRPC
comparison; service.py selects this one via its import.
"""
import logging

import grpc

from .config import settings
from .rag_client import rag_breaker  # reuse the existing breaker

log = logging.getLogger("ai-review-service.grpc-rag")

# context.proto ships at the app root (/app/context.proto, on sys.path).
_pb2, _pb2_grpc = grpc.protos_and_services("context.proto")


@rag_breaker
def _fetch_grpc(repo: str) -> str:
    with grpc.insecure_channel(settings.rag_grpc_target) as channel:
        stub = _pb2_grpc.ContextServiceStub(channel)
        reply = stub.GetContext(_pb2.ContextRequest(repo=repo, days=14), timeout=8.0)
        return reply.summary


def get_context(repo: str) -> tuple[str, bool]:
    """Return (context_summary, degraded?). Mirrors rag_client.get_context."""
    try:
        return _fetch_grpc(repo), False
    except Exception as exc:  # includes CircuitBreakerError and gRPC errors
        log.warning("gRPC RAG context unavailable for %s: %s", repo, exc)
        return "", True
