"""Build and cache project-context summaries.

Retrieves the top-K indexed chunks for a repo from Qdrant, asks Claude to
synthesize a short summary, and caches the result in Redis (TTL=1h).
"""
import json
import logging

import redis.asyncio as redis

from .claude_client import synthesize
from .config import settings
from .indexer import search

log = logging.getLogger("rag-context-service.context")

_redis = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)


def _cache_key(repo: str, days: int) -> str:
    return f"context:{repo}:{days}"


async def get_context(repo: str, days: int = 14, refresh: bool = False) -> dict:
    key = _cache_key(repo, days)
    if not refresh:
        cached = await _redis.get(key)
        if cached:
            data = json.loads(cached)
            data["cached"] = True
            return data

    chunks = search(query=f"recent activity in {repo}", repo=repo, limit=20)
    if not chunks:
        result = {"repo": repo, "summary": f"No indexed context yet for {repo}.",
                  "documents": 0, "cached": False}
        return result

    bullets = "\n".join(
        f"- [{c.get('type','doc')} #{c.get('number', c.get('sha','')[:7])}] "
        f"{c.get('title') or c.get('text','')[:120]}"
        for c in chunks[:20]
    )
    prompt = (
        f"You are summarizing recent GitHub activity for the repository '{repo}' "
        f"over the last {days} days. Produce a concise 3-5 line project-context "
        f"summary a developer can read to regain context. Mention recent merges, "
        f"open work, and any notable decisions.\n\nActivity:\n{bullets}"
    )
    try:
        summary = synthesize(prompt)
    except Exception as exc:
        log.warning("Claude synthesis failed (%s); returning raw activity summary", exc)
        summary = "Recent activity (AI summary unavailable):\n" + bullets
    result = {"repo": repo, "summary": summary, "documents": len(chunks), "cached": False}
    await _redis.set(key, json.dumps(result), ex=settings.cache_ttl_seconds)
    return result


async def session_block(repo: str, days: int = 14) -> str:
    ctx = await get_context(repo, days)
    return (
        f"=== Project Context: {repo} (last {days} days) ===\n"
        f"{ctx['summary']}\n"
        f"(indexed documents: {ctx['documents']})\n"
        f"=== End Context ==="
    )


async def redis_ping() -> bool:
    try:
        return await _redis.ping()
    except Exception:
        return False
