"""APScheduler-based poller: fallback to webhooks when a real token is set.

Disabled by default (GITHUB_POLL_ENABLED=false) because the token is a
placeholder locally. When enabled with a real PAT, it polls configured repos
every N minutes, persists rows, and publishes events.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .ingest import ingest_repo

log = logging.getLogger("github-service.poller")
scheduler = AsyncIOScheduler(timezone="UTC")


async def _poll_all() -> None:
    repos = [r.strip() for r in settings.github_repos.split(",") if r.strip()]
    for repo in repos:
        try:
            await ingest_repo(repo)
        except Exception as exc:  # circuit breaker / network — stay alive
            log.warning("Poll failed for %s: %s", repo, exc)


def start_poller() -> None:
    if not settings.github_poll_enabled:
        log.info("Poller disabled (GITHUB_POLL_ENABLED=false). Using webhook/simulate only.")
        return
    scheduler.add_job(
        _poll_all,
        "interval",
        minutes=settings.github_poll_interval_minutes,
        id="github-poll",
        next_run_time=None,
    )
    scheduler.start()
    log.info("Poller started: every %s min", settings.github_poll_interval_minutes)


def stop_poller() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
