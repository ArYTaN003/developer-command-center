"""Redis store: activity feed, dedup sets, and latest digest."""
import json
import time

import redis.asyncio as redis

from .config import settings

_redis = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)

_ACTIVITY_KEY = "notify:activity"        # list (recent events)
_DEDUP_PREFIX = "notify:seen:"           # per-event key with TTL (self-trimming)
_DIGEST_KEY = "notify:digest:latest"     # string (JSON)


async def ping() -> bool:
    try:
        return await _redis.ping()
    except Exception:
        return False


async def record_activity(event: dict) -> bool:
    """Store an event unless already seen (dedup). Returns True if newly stored.

    Dedup uses a per-event key with a TTL (SET NX EX) instead of one unbounded
    set, so the dedup footprint self-trims and can never leak memory forever.
    """
    event_id = event.get("id") or f"{event.get('type')}-{event.get('repo')}-{event.get('number')}"
    added = await _redis.set(
        _DEDUP_PREFIX + str(event_id), "1", nx=True, ex=settings.dedup_ttl_seconds
    )
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
