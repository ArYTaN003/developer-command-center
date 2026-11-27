"""AI reviewer: Claude call wrapped in a pybreaker circuit breaker.

Circuit breaker demo (configurable via env, defaults tuned for a fast demo):
  fail_max=2, reset_timeout=10s.
  - 2 consecutive Claude failures  -> breaker OPEN  -> fallback returned.
  - after reset_timeout            -> HALF-OPEN     -> next success -> CLOSED.

To demonstrate without a real key, toggle forced failures at runtime:
  POST /debug/claude-fail?enabled=true   (then trigger reviews)
  POST /debug/claude-fail?enabled=false  (then wait reset_timeout -> recovers)
"""
import logging

import pybreaker
from anthropic import Anthropic

from .config import settings

log = logging.getLogger("ai-review-service.reviewer")

FALLBACK = "[AI review unavailable — circuit open]"

claude_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.claude_breaker_fail_max,
    reset_timeout=settings.claude_breaker_reset_timeout,
    name="claude-api",
)

_force_fail = False  # flipped by the /debug/claude-fail endpoint for the demo

_client: Anthropic | None = None
if not settings.anthropic_is_placeholder:
    # Some Anthropic-compatible proxies authenticate via `Authorization: Bearer <key>`,
    # but the SDK sends `x-api-key` by default, so add the Bearer header explicitly.
    _client = Anthropic(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,
        default_headers={"Authorization": f"Bearer {settings.anthropic_api_key}"},
    )


def set_force_fail(enabled: bool) -> None:
    global _force_fail
    _force_fail = enabled
    log.warning("Claude forced-failure mode = %s", enabled)


@claude_breaker
def _call_claude(prompt: str) -> str:
    if _force_fail:
        raise RuntimeError("Forced Claude failure (demo)")
    if _client is None:
        # Placeholder key: deterministic local stub, counts as a success.
        return "[local-stub review] " + prompt.split("PR:")[-1][:200].strip()
    msg = _client.messages.create(
        model=settings.claude_model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def build_prompt(repo: str, pr: dict, context: str, template: dict) -> str:
    focus = template.get("focus_areas", "correctness, readability")
    ctx = f"Project context:\n{context}\n\n" if context else "(No project context available — degraded mode.)\n\n"
    return (
        f"You are a senior reviewer. Focus on: {focus}.\n\n"
        f"{ctx}"
        f"Review the following pull request and give a concise 4-6 bullet summary "
        f"of risks and suggestions.\n\n"
        f"PR: {repo} #{pr.get('number')} — {pr.get('title','')}\n"
        f"{pr.get('body','')}"
    )


def generate_review(repo: str, pr: dict, context: str, template: dict) -> tuple[str, bool]:
    """Return (review_text, degraded?). Never raises — always returns something."""
    prompt = build_prompt(repo, pr, context, template)
    try:
        return _call_claude(prompt), False
    except pybreaker.CircuitBreakerError:
        log.warning("Claude breaker OPEN -> fallback")
        return FALLBACK, True
    except Exception as exc:
        log.warning("Claude call failed: %s -> fallback", exc)
        return FALLBACK, True
