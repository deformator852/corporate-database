import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import Field, TypeAdapter, ValidationError

from api.ws import RECHECK_SECONDS, seconds_left, still_allowed
from database import AsyncSessionLocal
from exceptions import AppError
from models.audit import AuditAction
from models.user import User
from schemas.chat import (
    ChatAnswerSchema,
    ChatAskSchema,
    ChatCancelSchema,
    ChatCancelledSchema,
    ChatSocketErrorSchema,
)
from security import get_ws_payload
from services.audit import AuditService
from services.chat import ChatService
from services.embedding import EmbeddingModel, get_embedding_model
from services.generator import OllamaGenerator
from services.storage import ObjectStorage

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)

IncomingMessage = TypeAdapter(
    Annotated[ChatAskSchema | ChatCancelSchema, Field(discriminator="type")]
)


@router.websocket("/ws")
async def chat_socket(
    websocket: WebSocket,
    payload=Depends(get_ws_payload),
) -> None:
    try:
        user_id = int(payload.sub)
    except (TypeError, ValueError):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    ip = websocket.client.host if websocket.client else None
    embedder = get_embedding_model()
    generator = OllamaGenerator()
    storage = ObjectStorage()
    receive = asyncio.create_task(websocket.receive_text())
    reply: asyncio.Task[str] | None = None
    try:
        while True:
            wait: set[asyncio.Task] = {receive}
            if reply is not None:
                wait.add(reply)
            done, _pending = await asyncio.wait(
                wait,
                timeout=max(0.0, min(RECHECK_SECONDS, seconds_left(payload))),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                if not await _session_ok(websocket, payload):
                    return
                continue
            if receive in done:
                try:
                    raw = receive.result()
                except WebSocketDisconnect:
                    return
                if not await _session_ok(websocket, payload):
                    return
                receive = asyncio.create_task(websocket.receive_text())
                reply = await _on_client_message(
                    websocket,
                    user_id,
                    raw,
                    reply,
                    ip,
                    embedder,
                    generator,
                    storage,
                )
            if reply is not None and reply in done:
                await _finish_reply(websocket, reply)
                reply = None
    except WebSocketDisconnect:
        return
    finally:
        receive.cancel()
        if reply is not None and not reply.done():
            reply.cancel()
            try:
                await reply
            except (asyncio.CancelledError, AppError):
                pass


async def _session_ok(websocket: WebSocket, payload) -> bool:
    """Closes the socket once the session expires or is revoked. Checked on
    every client message and at least once a minute while idle."""
    code = await still_allowed(websocket, payload)
    if code is None:
        return True
    await websocket.close(code=code)
    return False


async def _on_client_message(
    websocket: WebSocket,
    user_id: int,
    raw: str,
    reply: asyncio.Task[str] | None,
    ip: str | None,
    embedder: EmbeddingModel,
    generator: OllamaGenerator,
    storage: ObjectStorage,
) -> asyncio.Task[str] | None:
    try:
        incoming = IncomingMessage.validate_json(raw)
    except ValidationError as exc:
        await websocket.send_json(
            ChatSocketErrorSchema(
                type="error",
                code="invalid",
                message=_validation_message(exc),
            ).model_dump()
        )
        return reply
    if isinstance(incoming, ChatCancelSchema):
        if reply is None:
            return None
        if reply.done():
            return reply
        reply.cancel()
        try:
            await reply
        except (asyncio.CancelledError, AppError):
            pass
        await websocket.send_json(ChatCancelledSchema(type="cancelled").model_dump())
        return None
    if reply is not None:
        await websocket.send_json(
            ChatSocketErrorSchema(
                type="error",
                code="invalid",
                message="A reply is already in progress.",
            ).model_dump()
        )
        return reply
    return asyncio.create_task(
        _generate(user_id, incoming, ip, embedder, generator, storage)
    )


async def _generate(
    user_id: int,
    ask: ChatAskSchema,
    ip: str | None,
    embedder: EmbeddingModel,
    generator: OllamaGenerator,
    storage: ObjectStorage,
) -> str:
    async with AsyncSessionLocal() as session:
        service = ChatService(session, embedder, generator, storage)
        content, documents = await service.reply(user_id, ask.messages)
        if documents:
            # Who read which documents through the assistant; not the question.
            actor = await session.get(User, user_id)
            AuditService(session, ip).record(
                AuditAction.CHAT_ANSWER,
                actor=actor,
                target_type="document",
                target_label=", ".join(str(d["name"]) for d in documents),
                details={
                    "documents": [
                        {
                            "id": d["document_id"],
                            "name": d["name"],
                            "classification": d["classification"],
                        }
                        for d in documents
                    ]
                },
            )
            await session.commit()
        return content


async def _finish_reply(websocket: WebSocket, reply: asyncio.Task[str]) -> None:
    try:
        content = reply.result()
    except asyncio.CancelledError:
        return
    except AppError as exc:
        await websocket.send_json(
            ChatSocketErrorSchema(
                type="error",
                code=exc.code,
                message=exc.message,
            ).model_dump()
        )
        return
    await websocket.send_json(ChatAnswerSchema(type="answer", content=content).model_dump())


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Enter a message."
    msg = errors[0].get("msg")
    if not isinstance(msg, str) or not msg:
        return "Enter a message."
    prefix = "Value error, "
    if msg.startswith(prefix):
        return msg[len(prefix) :]
    return msg
