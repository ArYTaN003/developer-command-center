"""RabbitMQ consumer: binds to github.events and indexes each event.

Robust connection with manual ack; on handler failure the message is nacked
and requeued so indexing can lag without losing events.
"""
import asyncio
import json
import logging

import aio_pika

from .config import settings
from .indexer import delete_by_pr, delete_by_repo, index_document

log = logging.getLogger("rag-context-service.consumer")

_ROUTING_KEYS = ["pr.opened", "pr.closed", "commit.pushed", "issue.created"]
# Untrack events (published by github-service on CRUD delete): purge the
# matching vectors so the RAG store doesn't serve stale context.
_UNTRACK_KEYS = ["repo.untracked", "pr.untracked"]


def _to_document(event: dict) -> tuple[str, str, dict]:
    etype = event.get("type", "doc")
    repo = event.get("repo", "unknown")
    if etype == "commit":
        doc_id = event["id"]
        text = f"Commit: {event.get('message','')} (by {event.get('author','')})"
        meta = {"repo": repo, "type": "commit", "sha": event.get("sha", "")}
    else:
        number = event.get("number")
        doc_id = event["id"]
        text = f"{etype} #{number}: {event.get('title','')}\n{event.get('body','')}"
        meta = {"repo": repo, "type": etype, "number": number,
                "title": event.get("title", "")}
    return doc_id, text, meta


async def _on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with message.process(requeue=False):
        event = json.loads(message.body.decode())
        etype = event.get("type", "")
        if etype == "repo.untracked":
            removed = delete_by_repo(event["repo"])
            log.info("repo.untracked %s -> purged %d points", event["repo"], removed)
        elif etype == "pr.untracked":
            number = event.get("number")
            if number is not None:
                removed = delete_by_pr(event["repo"], number)
            else:
                removed = delete_by_repo(event["repo"])
            log.info("pr.untracked %s#%s -> purged %d points", event["repo"], number, removed)
        else:
            doc_id, text, meta = _to_document(event)
            index_document(doc_id, text, meta)


async def run_consumer() -> None:
    conn = await aio_pika.connect_robust(settings.amqp_url)
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=10)
    exchange = await channel.declare_exchange(
        settings.rabbitmq_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
    )
    # Dead-letter exchange + queue: a message that fails processing is routed here
    # instead of being requeued forever (poison-message protection).
    dlx = await channel.declare_exchange("dlx", aio_pika.ExchangeType.DIRECT, durable=True)
    dead_queue = await channel.declare_queue("rag-context.index.dead", durable=True)
    await dead_queue.bind(dlx, routing_key="rag-context.index.dead")
    queue = await channel.declare_queue(
        "rag-context.index", durable=True,
        arguments={"x-dead-letter-exchange": "dlx",
                   "x-dead-letter-routing-key": "rag-context.index.dead"},
    )
    for key in _ROUTING_KEYS + _UNTRACK_KEYS:
        await queue.bind(exchange, routing_key=key)
    log.info("rag consumer bound to %s (DLQ: rag-context.index.dead)",
             _ROUTING_KEYS + _UNTRACK_KEYS)
    await queue.consume(_on_message)
    await asyncio.Future()  # run forever
