"""Sync REST client to github-service for PR diffs.

Lets the reviewer see the actual changed code, not just the PR title/body.
Degrades gracefully: if github-service is unreachable or has no write/read token,
the reviewer proceeds from metadata/context only rather than failing.
"""
import logging

import httpx

from .config import settings

log = logging.getLogger("ai-review-service.github")


def fetch_pr_diff(repo: str, number: int) -> dict:
    """Return the diff payload from github-service, or {} on any failure."""
    if not number:
        return {}
    try:
        url = f"{settings.github_service_url}/repos/{repo}/prs/{number}/diff"
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning("diff fetch failed for %s #%s: %s", repo, number, exc)
        return {}
