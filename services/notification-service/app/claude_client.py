"""Claude client with offline fallback for digest synthesis."""
from anthropic import Anthropic

from .config import settings

_client: Anthropic | None = None
if not settings.anthropic_is_placeholder:
    # Some Anthropic-compatible proxies authenticate via `Authorization: Bearer <key>`,
    # but the SDK sends `x-api-key` by default, so add the Bearer header explicitly.
    _client = Anthropic(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,
        default_headers={"Authorization": f"Bearer {settings.anthropic_api_key}"},
    )


def synthesize(prompt: str, max_tokens: int = 350) -> str:
    if _client is None:
        return "[local-stub digest] " + prompt[:260].replace("\n", " ")
    msg = _client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")
