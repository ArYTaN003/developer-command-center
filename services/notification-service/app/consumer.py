"""RabbitMQ consumer: collect activity (github.events) + alerts (notifications).

Deduplicates via a Redis set so a replayed or duplicated event is only counted
once in the digest.
"""
import asyncio
import json
import logging

import aio_pika

from .config import settings
from .redis_store import record_activity

log = logging.getLogger("notification-service.consumer")


async def _on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with message.process(requeue=True):
        event = json.loads(message.body.decode())
        new = await record_activity(event)
        log.info("Activity %s (new=%s)", event.get("id"), new)


async def run_consumer() -> None:
    conn = await aio_pika.connect_robust(settings.amqp_url)
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=10)

    # github.events (activity feed)
    events_exchange = await channel.declare_exchange(
        settings.rabbitmq_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue("notification.activity", durable=True)
    for key in ["pr.opened", "pr.closed", "commit.pushed", "issue.created"]:
        await queue.bind(events_exchange, routing_key=key)

    # notifications exchange (direct alerts) — declared for architectural completeness
    notif_exchange = await channel.declare_exchange(
        settings.rabbitmq_notifications_exchange, aio_pika.ExchangeType.DIRECT, durable=True
    )
    await queue.bind(notif_exchange, routing_key="alert")

    log.info("notification consumer bound to github.events + notifications")
    await queue.consume(_on_message)
    await asyncio.Future()
