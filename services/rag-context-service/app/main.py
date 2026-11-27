"""rag-context-service FastAPI app."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from .config import settings
from .consumer import run_consumer
from .context import get_context, redis_ping, session_block
from .indexer import count, ensure_collection, index_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("rag-context-service")


async def _ensure_collection_with_retry(attempts: int = 30, delay: float = 2.0) -> None:
    for i in range(attempts):
        try:
            ensure_collection()
            return
        except Exception as exc:
            log.warning("Qdrant not ready (%d/%d): %s", i + 1, attempts, exc)
            await asyncio.sleep(delay)
    log.error("Qdrant unreachable after retries; continuing (will retry on first use)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _ensure_collection_with_retry()
    consumer_task = asyncio.create_task(run_consumer())
    log.info("rag-context-service ready")
    yield
    consumer_task.cancel()


app = FastAPI(title="rag-context-service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    try:
        indexed = count()
    except Exception:
        indexed = -1   # Qdrant briefly unavailable; stay live for readiness
    return {"status": "ok", "service": settings.service_name,
            "redis": await redis_ping(), "indexed": indexed}


@app.get("/context")
async def context(repo: str, days: int = 14, refresh: bool = False):
    return await get_context(repo, days, refresh)


@app.get("/session-start")
async def session_start(repo: str, days: int = 14):
    """Paste-ready context block for a new Claude Code session."""
    return {"repo": repo, "block": await session_block(repo, days)}


class IndexRequest(BaseModel):
    doc_id: str
    text: str
    repo: str
    type: str = "doc"


@app.post("/index")
async def index(req: IndexRequest):
    index_document(req.doc_id, req.text, {"repo": req.repo, "type": req.type})
    return {"indexed": req.doc_id, "total": count()}
