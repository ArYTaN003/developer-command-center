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
    # requeue=False: a bad/poison message is NACKed to the dead-letter exchange
    # instead of being requeued forever (which caused a hot loop / CPU spin).
    try:
        async with message.process(requeue=False):
            event = json.loads(message.body.decode())
            new = await record_activity(event)
            log.info("Activity %s (new=%s)", event.get("id"), new)
    except Exception as exc:
        # message.process already NACKed (requeue=False) → routed to DLQ.
        deaths = 0
        try:
            deaths = (message.headers or {}).get("x-death", [{}])[0].get("count", 0)
        except Exception:
            pass
        log.warning("Dead-lettering message (prior deaths=%s): %s", deaths, exc)


async def run_consumer() -> None:
    conn = await aio_pika.connect_robust(settings.amqp_url)
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=10)

    # Dead-letter exchange + queue for poison / persistently failing messages.
    dlx = await channel.declare_exchange("dlx", aio_pika.ExchangeType.DIRECT, durable=True)
    dead_queue = await channel.declare_queue("notification.activity.dead", durable=True)
    await dead_queue.bind(dlx, routing_key="notification.activity.dead")

    # github.events (activity feed) — main queue routes failures to the DLX.
    events_exchange = await channel.declare_exchange(
        settings.rabbitmq_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(
        "notification.activity", durable=True,
        arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "notification.activity.dead",
        },
    )
    for key in ["pr.opened", "pr.closed", "commit.pushed", "issue.created"]:
        await queue.bind(events_exchange, routing_key=key)

    # notifications exchange (direct alerts) — now genuinely published to by github-service.
    notif_exchange = await channel.declare_exchange(
        settings.rabbitmq_notifications_exchange, aio_pika.ExchangeType.DIRECT, durable=True
    )
    await queue.bind(notif_exchange, routing_key="alert")

    log.info("notification consumer bound to github.events + notifications (DLQ: notification.activity.dead)")
    await queue.consume(_on_message)
    await asyncio.Future()
