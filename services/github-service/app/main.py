"""github-service FastAPI app.

Ingests GitHub activity (live via PAT, or locally via /webhook and /simulate)
and publishes events to the RabbitMQ github.events topic exchange.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from pydantic import BaseModel

from .config import settings
from .github_client import github_breaker
from .ingest import (
    ingest_repo, list_prs, list_repos,
    record_commit, record_issue, record_pull_request,
)
from .models import init_db
from .poller import start_poller, stop_poller
from .publisher import publisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("github-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await publisher.connect()
    start_poller()
    log.info("github-service ready")
    yield
    stop_poller()
    await publisher.close()


app = FastAPI(title="github-service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.service_name}


@app.get("/breaker")
async def breaker_state():
    return {"name": github_breaker.name, "state": github_breaker.current_state,
            "fail_counter": github_breaker.fail_counter}


@app.get("/repos")
async def repos():
    return {"repos": await list_repos()}


@app.get("/repos/{owner}/{repo}/prs")
async def repo_prs(owner: str, repo: str):
    full = f"{owner}/{repo}"
    return {"repo": full, "pull_requests": await list_prs(full)}


@app.post("/poll")
async def poll_now(repo: str | None = None):
    """Manually trigger a live poll (needs a real GITHUB_TOKEN)."""
    target = repo or settings.github_repos.split(",")[0].strip()
    return await ingest_repo(target)


# -------- Webhook: real GitHub webhook payloads land here --------
@app.post("/webhook")
async def webhook(request: Request):
    event = request.headers.get("X-GitHub-Event", "")
    body = await request.json()
    repo = (body.get("repository") or {}).get("full_name", "unknown/unknown")

    if event == "pull_request" and "pull_request" in body:
        await record_pull_request(repo, body["pull_request"])
        return {"handled": "pull_request"}
    if event == "issues" and "issue" in body:
        await record_issue(repo, body["issue"])
        return {"handled": "issue"}
    if event == "push":
        for c in body.get("commits", []):
            await record_commit(repo, c)
        return {"handled": "push", "commits": len(body.get("commits", []))}
    return {"handled": "ignored", "event": event}


# -------- Simulate: drive the whole pipeline locally with no token --------
class SimulateRequest(BaseModel):
    repo: str = "myorg/backend"
    title: str = "Add async request handlers"
    number: int = 142
    author: str = "dev"
    body: str = "Refactor sync handlers to async for throughput; touches auth middleware."


@app.post("/simulate/pr")
async def simulate_pr(req: SimulateRequest):
    """Emit a synthetic pr.opened event (persist + publish) for demos."""
    pr = {
        "number": req.number, "title": req.title, "state": "open",
        "user": {"login": req.author}, "body": req.body,
    }
    payload = await record_pull_request(req.repo, pr)
    return {"simulated": "pr.opened", "payload": payload}


@app.post("/simulate/commit")
async def simulate_commit(repo: str = "myorg/backend", message: str = "Fix null pointer in parser"):
    payload = await record_commit(repo, {"sha": "deadbeefcafe", "message": message,
                                         "author": "dev"})
    return {"simulated": "commit.pushed", "payload": payload}
