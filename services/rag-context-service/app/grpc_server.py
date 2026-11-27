"""gRPC ContextService server (Lab 3B: synchronous gRPC between services).

Exposes GetContext over gRPC alongside the REST GET /context endpoint, so the
project demonstrates BOTH synchronous communication styles. The .proto is
compiled in-memory at import time via grpc's dynamic loader (requires
grpcio-tools), so there is no separate code-generation step or committed stubs.
"""
import logging

import grpc

from .config import settings
from .context import get_context

log = logging.getLogger("rag-context-service.grpc")

# context.proto ships at the app root (/app/context.proto, on sys.path).
_pb2, _pb2_grpc = grpc.protos_and_services("context.proto")


class ContextServicer(_pb2_grpc.ContextServiceServicer):
    async def GetContext(self, request, context):  # noqa: N802 (gRPC method name)
        data = await get_context(request.repo, request.days or 14)
        return _pb2.ContextReply(
            repo=data.get("repo", request.repo),
            summary=data.get("summary", ""),
            documents=int(data.get("documents", 0)),
        )


async def serve_grpc(port: int = 50051) -> None:
    """Run the async gRPC server until cancelled."""
    server = grpc.aio.server()
    _pb2_grpc.add_ContextServiceServicer_to_server(ContextServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    log.info("gRPC ContextService listening on :%d", port)
    await server.wait_for_termination()
