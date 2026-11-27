"""RabbitMQ consumer: pr.opened events trigger an AI review."""
import asyncio
import json
import logging

import aio_pika

from .config import settings
from .service import run_review

log = logging.getLogger("ai-review-service.consumer")


async def _on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with message.process(requeue=False):
        event = json.loads(message.body.decode())
        repo = event.get("repo", "unknown")
        result = await run_review(repo, event)
        log.info("Reviewed %s (degraded=%s)", result["pr_id"], result["degraded"])


async def run_consumer() -> None:
    conn = await aio_pika.connect_robust(settings.amqp_url)
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=4)
    exchange = await channel.declare_exchange(
        settings.rabbitmq_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
    )
    # Dead-letter exchange + queue: a failing review message is routed here
    # instead of being requeued forever (poison-message protection).
    dlx = await channel.declare_exchange("dlx", aio_pika.ExchangeType.DIRECT, durable=True)
    dead_queue = await channel.declare_queue("ai-review.pr-opened.dead", durable=True)
    await dead_queue.bind(dlx, routing_key="ai-review.pr-opened.dead")
    queue = await channel.declare_queue(
        "ai-review.pr-opened", durable=True,
        arguments={"x-dead-letter-exchange": "dlx",
                   "x-dead-letter-routing-key": "ai-review.pr-opened.dead"},
    )
    await queue.bind(exchange, routing_key="pr.opened")
    log.info("ai-review consumer bound to pr.opened (DLQ: ai-review.pr-opened.dead)")
    await queue.consume(_on_message)
    await asyncio.Future()
