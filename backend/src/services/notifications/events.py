import json
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika import ExchangeType, Message

from models.notification import Notification
from settings import NOTIFICATION_EVENTS_EXCHANGE, rabbitmq_url

NotificationEvent = dict[str, object]


def notification_event(notification: Notification) -> NotificationEvent:
    created_at = notification.created_at.isoformat() if notification.created_at else None
    return {
        "id": notification.id,
        "user_id": notification.user_id,
        "type": notification.type,
        "message": notification.message,
        "read": notification.read,
        "created_at": created_at,
    }


class NotificationEventPublisher:
    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None

    async def publish(self, notification: Notification) -> None:
        connection = await self._ensure_connection()
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            NOTIFICATION_EVENTS_EXCHANGE,
            ExchangeType.FANOUT,
            durable=True,
        )
        body = json.dumps(notification_event(notification)).encode()
        await exchange.publish(
            Message(body=body, content_type="application/json"),
            routing_key="",
        )
        await channel.close()

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None

    async def _ensure_connection(self) -> aio_pika.RobustConnection:
        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(rabbitmq_url())
        return self._connection


async def consume_notification_events(
    on_event: Callable[[NotificationEvent], Awaitable[None]],
) -> None:
    connection = await aio_pika.connect_robust(rabbitmq_url())
    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            NOTIFICATION_EVENTS_EXCHANGE,
            ExchangeType.FANOUT,
            durable=True,
        )
        queue = await channel.declare_queue(exclusive=True)
        await queue.bind(exchange)
        async with queue.iterator() as messages:
            async for message in messages:
                async with message.process():
                    try:
                        payload = json.loads(message.body.decode())
                    except UnicodeDecodeError, json.JSONDecodeError:
                        continue
                    try:
                        await on_event(payload)
                    except Exception:
                        continue
    finally:
        await connection.close()
