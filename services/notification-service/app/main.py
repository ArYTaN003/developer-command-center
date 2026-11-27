"""notification-service FastAPI app."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .config import settings
from .consumer import run_consumer
from .digest import build_digest, start_scheduler, stop_scheduler
from .redis_store import latest_digest, ping, recent_activity

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("notification-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_consumer())
    start_scheduler()
    log.info("notification-service ready")
    yield
    stop_scheduler()
    consumer_task.cancel()


app = FastAPI(title="notification-service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.service_name, "redis": await ping()}


@app.get("/activity")
async def activity(limit: int = 50):
    return {"activity": await recent_activity(limit)}


@app.get("/digest/latest")
async def digest_latest():
    d = await latest_digest()
    if not d:
        raise HTTPException(404, "No digest generated yet. POST /digest/trigger first.")
    return d


@app.post("/digest/trigger")
async def digest_trigger():
    return await build_digest()
