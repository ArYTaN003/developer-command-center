"""ai-review-service FastAPI app."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import settings
from .consumer import run_consumer
from .models import init_db
from .rag_client import rag_breaker
from .reviewer import claude_breaker, set_force_fail
from .service import (
    get_review, list_templates, recent_reviews, run_review, upsert_template,
    delete_template,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("ai-review-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(run_consumer())
    log.info("ai-review-service ready")
    yield
    consumer_task.cancel()


app = FastAPI(title="ai-review-service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.service_name}


@app.get("/breaker")
async def breaker_state():
    return {
        "claude": {"state": claude_breaker.current_state, "fails": claude_breaker.fail_counter,
                   "fail_max": settings.claude_breaker_fail_max,
                   "reset_timeout": settings.claude_breaker_reset_timeout},
        "rag": {"state": rag_breaker.current_state, "fails": rag_breaker.fail_counter},
    }


class TriggerRequest(BaseModel):
    repo: str
    number: int
    title: str = ""
    body: str = ""


@app.post("/reviews/trigger")
async def trigger(req: TriggerRequest):
    return await run_review(req.repo, req.model_dump())


@app.get("/reviews/recent")
async def reviews_recent(limit: int = 10):
    return {"reviews": await recent_reviews(limit)}


@app.get("/reviews/{pr_id}")
async def review_by_pr(pr_id: str):
    r = await get_review(pr_id)
    if not r:
        raise HTTPException(404, f"No review for {pr_id}")
    return r


class TemplateRequest(BaseModel):
    repo_pattern: str
    focus_areas: str
    language: str = "general"


@app.post("/templates")
async def add_template(req: TemplateRequest):
    return await upsert_template(req.repo_pattern, req.focus_areas, req.language)


@app.get("/templates")
async def get_templates():
    return {"templates": await list_templates()}


class TemplateUpdate(BaseModel):
    focus_areas: str
    language: str = "general"


@app.put("/templates/{repo_pattern:path}")
async def update_template(repo_pattern: str, req: TemplateUpdate):
    """CRUD: Update — upsert the template at this repo_pattern."""
    return await upsert_template(repo_pattern, req.focus_areas, req.language)


@app.delete("/templates/{repo_pattern:path}")
async def remove_template(repo_pattern: str):
    """CRUD: Delete — remove the template at this repo_pattern."""
    result = await delete_template(repo_pattern)
    if result["deleted"] == 0:
        raise HTTPException(404, f"No template for pattern {repo_pattern!r}")
    return result


@app.post("/debug/claude-fail")
async def debug_claude_fail(enabled: bool):
    """Toggle forced Claude failures to demo the circuit breaker without a key."""
    set_force_fail(enabled)
    return {"force_fail": enabled, "breaker_state": claude_breaker.current_state}
