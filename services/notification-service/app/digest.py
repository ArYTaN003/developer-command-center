"""Daily digest: aggregate recent activity + reviews, synthesize via Claude."""
import logging
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .claude_client import synthesize
from .config import settings
from .redis_store import recent_activity, save_digest

log = logging.getLogger("notification-service.digest")
scheduler = AsyncIOScheduler(timezone="UTC")


async def _fetch_recent_reviews() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            resp = await c.get(f"{settings.ai_review_url}/reviews/recent", params={"limit": 10})
            resp.raise_for_status()
            return resp.json().get("reviews", [])
    except Exception as exc:
        log.warning("Could not fetch reviews for digest: %s", exc)
        return []


async def _deliver_to_slack(text: str) -> None:
    """Push the digest to a Slack incoming webhook, if one is configured."""
    if not settings.slack_webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            resp = await c.post(settings.slack_webhook_url, json={"text": text})
            resp.raise_for_status()
        log.info("Digest delivered to Slack")
    except Exception as exc:
        log.warning("Slack delivery failed: %s", exc)


async def build_digest() -> dict:
    activity = await recent_activity(50)
    reviews = await _fetch_recent_reviews()

    activity_lines = "\n".join(
        f"- {a.get('type','event')} {a.get('repo','')} "
        f"#{a.get('number', a.get('sha','')[:7])}: {a.get('title', a.get('message',''))[:100]}"
        for a in activity[:20]
    ) or "- (no recent activity)"
    review_lines = "\n".join(
        f"- review {r.get('repo','')} {r.get('pr_id','')}: {r.get('summary','')[:120]}"
        for r in reviews[:10]
    ) or "- (no recent reviews)"

    prompt = (
        "Write a developer's morning digest in at most 200 words. Be concise and "
        "actionable. Group by: open work, recent merges, reviews needing attention, "
        "blockers.\n\n"
        f"Recent activity:\n{activity_lines}\n\nRecent AI reviews:\n{review_lines}"
    )
    try:
        text = synthesize(prompt)
    except Exception as exc:
        log.warning("Claude digest synthesis failed (%s); returning plain digest", exc)
        text = ("Digest (AI summary unavailable):\n\nActivity:\n" + activity_lines
                + "\n\nReviews:\n" + review_lines)
    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "activity_count": len(activity),
        "review_count": len(reviews),
        "digest": text,
    }
    await save_digest(digest)
    await _deliver_to_slack(text)
    log.info("Digest generated (%d activity, %d reviews)", len(activity), len(reviews))
    return digest


def start_scheduler() -> None:
    scheduler.add_job(
        build_digest, "cron",
        hour=settings.digest_cron_hour, minute=settings.digest_cron_minute,
        id="daily-digest",
    )
    scheduler.start()
    log.info("Digest scheduled daily at %02d:%02d UTC",
             settings.digest_cron_hour, settings.digest_cron_minute)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
