"""GitHub REST client wrapped in a pybreaker circuit breaker.

The token is a placeholder by default; when it is a placeholder we skip the
real network call and raise, so the circuit breaker / fallback path is the
one exercised locally. Replace GITHUB_TOKEN with a real PAT to go live.
"""
import logging

import httpx
import pybreaker
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import settings

log = logging.getLogger("github-service.client")

# Circuit breaker: opens after N consecutive failures, resets after timeout.
github_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.github_breaker_fail_max,
    reset_timeout=settings.github_breaker_reset_timeout,
    name="github-api",
)


class GitHubClient:
    def __init__(self) -> None:
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {settings.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @github_breaker
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=5))
    async def _get(self, path: str) -> list | dict:
        if settings.github_token_is_placeholder:
            raise RuntimeError(
                "GITHUB_TOKEN is a placeholder — set a real PAT to call GitHub."
            )
        url = f"{settings.github_api_url}{path}"
        async with httpx.AsyncClient(timeout=10.0, headers=self._headers) as c:
            resp = await c.get(url)
            resp.raise_for_status()
            return resp.json()

    async def list_pull_requests(self, repo: str) -> list[dict]:
        return await self._get(f"/repos/{repo}/pulls?state=all&per_page=20")  # type: ignore

    async def list_issues(self, repo: str) -> list[dict]:
        return await self._get(f"/repos/{repo}/issues?state=all&per_page=20")  # type: ignore

    async def list_commits(self, repo: str) -> list[dict]:
        return await self._get(f"/repos/{repo}/commits?per_page=20")  # type: ignore


client = GitHubClient()
