"""github-service FastAPI app.

Ingests GitHub activity (live via PAT, or locally via /webhook and /simulate)
and publishes events to the RabbitMQ github.events topic exchange.
"""
import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager

import httpx
import pybreaker
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .config import settings
from .github_client import client, github_breaker
from .ingest import (
    delete_pr, delete_repo, ingest_repo, list_prs, list_repos, mark_pr_merged,
    record_commit, record_issue, record_pull_request, update_repo_pr,
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


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Guard mutating endpoints when an api_key is configured (empty default = open)."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


async def _github_call(awaitable):
    """Run a GitHub API call, translating failures into clear HTTP errors."""
    try:
        return await awaitable
    except pybreaker.CircuitBreakerError:
        raise HTTPException(status_code=503,
                            detail="GitHub circuit breaker is open — try again shortly.")
    except RuntimeError as exc:  # placeholder token / write not available
        raise HTTPException(status_code=409, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code,
                            detail=f"GitHub API error: {exc.response.text[:300]}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub request failed: {exc}")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.service_name,
            "github_write_enabled": not settings.github_token_is_placeholder}


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
async def poll_now(repo: str | None = None, _: None = Depends(require_api_key)):
    """Manually trigger a live poll (needs a real GITHUB_TOKEN)."""
    target = repo or settings.github_repos.split(",")[0].strip()
    return await ingest_repo(target)


# -------- Webhook: real GitHub webhook payloads land here --------
@app.post("/webhook")
async def webhook(request: Request):
    raw = await request.body()
    # HMAC verification (only enforced when a webhook_secret is configured).
    if settings.webhook_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            settings.webhook_secret.encode(), raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event", "")
    body = json.loads(raw or b"{}")
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
async def simulate_pr(req: SimulateRequest, _: None = Depends(require_api_key)):
    """Emit a synthetic pr.opened event (persist + publish) for demos."""
    pr = {
        "number": req.number, "title": req.title, "state": "open",
        "user": {"login": req.author}, "body": req.body,
    }
    payload = await record_pull_request(req.repo, pr)
    return {"simulated": "pr.opened", "payload": payload}


@app.post("/simulate/commit")
async def simulate_commit(repo: str = "myorg/backend", message: str = "Fix null pointer in parser",
                          _: None = Depends(require_api_key)):
    payload = await record_commit(repo, {"sha": "deadbeefcafe", "message": message,
                                         "author": "dev"})
    return {"simulated": "commit.pushed", "payload": payload}


# ======== PR actions (Update / Delete verbs) ========
class CommentRequest(BaseModel):
    body: str


class PRUpdate(BaseModel):
    title: str | None = None
    state: str | None = None
    body: str | None = None


@app.put("/repos/{owner}/{repo}/prs/{number}/merge")
async def merge_pr(owner: str, repo: str, number: int):
    """Merge a PR on GitHub (requires a real token with write scope)."""
    full = f"{owner}/{repo}"
    result = await _github_call(client.merge_pull_request(full, number, settings.merge_method))
    await mark_pr_merged(full, number)
    return {"merged": True, "repo": full, "number": number,
            "sha": (result or {}).get("sha"), "message": (result or {}).get("message")}


@app.post("/repos/{owner}/{repo}/prs/{number}/comments")
async def comment_pr(owner: str, repo: str, number: int, req: CommentRequest):
    """Post a comment onto a PR on GitHub (requires a real token with write scope)."""
    full = f"{owner}/{repo}"
    body = (req.body or "").strip()
    if not body:
        raise HTTPException(status_code=422, detail="Comment body must not be empty.")
    result = await _github_call(client.comment_on_pull_request(full, number, body))
    return {"commented": True, "repo": full, "number": number,
            "comment_url": (result or {}).get("html_url")}


@app.delete("/repos/{owner}/{repo}/prs/{number}/branch")
async def delete_pr_branch(owner: str, repo: str, number: int):
    """Delete the head branch of a PR, but only if it is merged on GitHub."""
    full = f"{owner}/{repo}"
    pr = await _github_call(client.get_pull_request(full, number))
    if not (pr or {}).get("merged"):
        raise HTTPException(status_code=409,
                            detail="PR is not merged on GitHub; refusing to delete its branch.")
    branch = ((pr.get("head") or {}).get("ref")) if pr else None
    if not branch:
        raise HTTPException(status_code=422, detail="Could not resolve the PR head branch.")
    await _github_call(client.delete_branch(full, branch))
    return {"deleted_branch": branch, "repo": full, "number": number}


@app.put("/repos/{owner}/{repo}/prs/{number}")
async def update_pr(owner: str, repo: str, number: int, req: PRUpdate):
    """Explicit local Update of a tracked PR's title/state/body."""
    return await update_repo_pr(f"{owner}/{repo}", number, req.model_dump(exclude_none=True))


@app.delete("/repos/{owner}/{repo}/prs/{number}")
async def untrack_pr(owner: str, repo: str, number: int):
    """Stop tracking one PR locally (non-destructive to GitHub)."""
    return await delete_pr(f"{owner}/{repo}", number)


@app.delete("/repos/{owner}/{repo}")
async def untrack_repo(owner: str, repo: str):
    """Stop tracking a repo and all its activity locally (non-destructive to GitHub)."""
    return await delete_repo(f"{owner}/{repo}")


@app.get("/repos/{owner}/{repo}/prs/{number}/diff")
async def pr_diff(owner: str, repo: str, number: int, max_chars: int | None = None):
    """Return a PR's unified diff (bounded) + changed-file summary — for reviewers.

    Read-only: needs a token with read scope (contents/pull_requests), not write.
    """
    full = f"{owner}/{repo}"
    limit = max_chars if (max_chars and max_chars > 0) else settings.max_diff_chars
    diff = await _github_call(client.get_pull_request_diff(full, number))
    files = await _github_call(client.list_pull_request_files(full, number))
    file_meta = [
        {"filename": f.get("filename"), "status": f.get("status"),
         "additions": f.get("additions"), "deletions": f.get("deletions"),
         "changes": f.get("changes")}
        for f in (files or [])
    ]
    return {
        "repo": full, "number": number,
        "files": file_meta, "file_count": len(file_meta),
        "diff_chars": len(diff), "returned_chars": min(len(diff), limit),
        "truncated": len(diff) > limit, "diff": diff[:limit],
    }
