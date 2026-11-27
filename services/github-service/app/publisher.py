"""RabbitMQ publisher (aio-pika) for the github.events topic exchange.

Producers never know who consumes — rag/ai/notification services bind their
own queues. Reconnect-tolerant: a single durable connection + channel.
"""
import json
import logging

import aio_pika

from .config import settings

log = logging.getLogger("github-service.publisher")


class Publisher:
    def __init__(self) -> None:
        self._conn: aio_pika.abc.AbstractRobustConnection | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        self._conn = await aio_pika.connect_robust(settings.amqp_url)
        channel = await self._conn.channel(publisher_confirms=True)
        self._exchange = await channel.declare_exchange(
            settings.rabbitmq_events_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        log.info("Publisher connected to exchange %s", settings.rabbitmq_events_exchange)

    async def publish(self, routing_key: str, payload: dict) -> None:
        if self._exchange is None:
            raise RuntimeError("Publisher not connected")
        message = aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=routing_key)
        log.info("Published %s -> %s", routing_key, payload.get("id") or payload.get("number"))

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()


publisher = Publisher()
