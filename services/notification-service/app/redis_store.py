"""Redis store: activity feed, dedup sets, and latest digest."""
import json
import time

import redis.asyncio as redis

from .config import settings

_redis = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)

_ACTIVITY_KEY = "notify:activity"        # list (recent events)
_DEDUP_KEY = "notify:seen"               # set (event ids already processed)
_DIGEST_KEY = "notify:digest:latest"     # string (JSON)


async def ping() -> bool:
    try:
        return await _redis.ping()
    except Exception:
        return False


async def record_activity(event: dict) -> bool:
    """Store an event unless already seen (dedup). Returns True if newly stored."""
    event_id = event.get("id") or f"{event.get('type')}-{event.get('repo')}-{event.get('number')}"
    added = await _redis.sadd(_DEDUP_KEY, event_id)
    if not added:
        return False
    entry = json.dumps({"ts": time.time(), **event})
    await _redis.lpush(_ACTIVITY_KEY, entry)
    await _redis.ltrim(_ACTIVITY_KEY, 0, 199)  # keep last 200
    return True


async def recent_activity(limit: int = 50) -> list[dict]:
    rows = await _redis.lrange(_ACTIVITY_KEY, 0, limit - 1)
    return [json.loads(r) for r in rows]


async def save_digest(digest: dict) -> None:
    await _redis.set(_DIGEST_KEY, json.dumps(digest))


async def latest_digest() -> dict | None:
    raw = await _redis.get(_DIGEST_KEY)
    return json.loads(raw) if raw else None
