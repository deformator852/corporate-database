import json
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika import ExchangeType, Message

from models.document import Document
from settings import DOCUMENT_EVENTS_EXCHANGE, rabbitmq_url

DocumentEvent = dict[str, object]


def document_event(document: Document) -> DocumentEvent:
    created_at = document.created_at.isoformat() if document.created_at else None
    return {
        "id": document.id,
        "name": document.name,
        "filename": document.filename,
        "status": document.status,
        "progress": document.progress,
        "error_message": document.error_message,
        "classification": document.classification,
        "created_at": created_at,
    }


class DocumentEventPublisher:
    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None

    async def publish(self, document: Document) -> None:
        connection = await self._ensure_connection()
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            DOCUMENT_EVENTS_EXCHANGE,
            ExchangeType.FANOUT,
            durable=True,
        )
        body = json.dumps(document_event(document)).encode()
        await exchange.publish(Message(body=body, content_type="application/json"), routing_key="")
        await channel.close()

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None

    async def _ensure_connection(self) -> aio_pika.RobustConnection:
        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(rabbitmq_url())
        return self._connection


async def consume_document_events(
    on_event: Callable[[DocumentEvent], Awaitable[None]],
) -> None:
    connection = await aio_pika.connect_robust(rabbitmq_url())
    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            DOCUMENT_EVENTS_EXCHANGE,
            ExchangeType.FANOUT,
            durable=True,
        )
        queue = await channel.declare_queue(exclusive=True)
        await queue.bind(exchange)
        async with queue.iterator() as messages:
            async for message in messages:
                async with message.process():
                    payload = json.loads(message.body.decode())
                    await on_event(payload)
    finally:
        await connection.close()
