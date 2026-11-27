"""Claude/Anthropic client with graceful offline fallback.

When ANTHROPIC_API_KEY is a placeholder, returns a deterministic local stub so
the RAG pipeline is demonstrable without a key. Replace the key to go live.
"""
import logging

from anthropic import Anthropic

from .config import settings

log = logging.getLogger("rag-context-service.claude")

_client: Anthropic | None = None
if not settings.anthropic_is_placeholder:
    # Some Anthropic-compatible proxies authenticate via `Authorization: Bearer <key>`,
    # but the SDK sends `x-api-key` by default, so add the Bearer header explicitly.
    _client = Anthropic(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,
        default_headers={"Authorization": f"Bearer {settings.anthropic_api_key}"},
    )


def synthesize(prompt: str, max_tokens: int = 400) -> str:
    if _client is None:
        return "[local-stub summary] " + prompt[:280].replace("\n", " ")
    msg = _client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")
