import asyncio
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import Field, TypeAdapter, ValidationError

from api.deps import get_chat_history_service, get_current_user
from api.ws import RECHECK_SECONDS, seconds_left, still_allowed
from database import AsyncSessionLocal
from exceptions import AppError
from i18n import t
from models.audit import AuditAction
from models.user import User
from schemas.chat import (
    ChatAnswerSchema,
    ChatAskSchema,
    ChatCancelSchema,
    ChatCancelledSchema,
    ChatConversationListSchema,
    ChatConversationSchema,
    ChatDeltaSchema,
    ChatSocketErrorSchema,
    ChatSourceSchema,
)
from schemas.error import ErrorSchema, validation_message
from security import get_ws_payload
from services.audit import AuditService
from services.chat import ChatService
from services.chat_history import ChatHistoryService
from services.chat_limit import finish_chat_request, start_chat_request
from services.embedding import EmbeddingModel, get_embedding_model
from services.generator import OllamaGenerator

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)

@router.get(
    "/conversations",
    response_model=ChatConversationListSchema,
    responses={401: {"model": ErrorSchema}},
)
async def list_conversations(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
    user: User = Depends(get_current_user),
    history: ChatHistoryService = Depends(get_chat_history_service),
) -> ChatConversationListSchema:
    items, total = await history.list_conversations(user.id, page=page, per_page=per_page)
    return ChatConversationListSchema.from_page(items, page=page, per_page=per_page, total=total)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ChatConversationSchema,
    responses={401: {"model": ErrorSchema}, 404: {"model": ErrorSchema}},
)
async def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    history: ChatHistoryService = Depends(get_chat_history_service),
) -> ChatConversationSchema:
    conversation = await history.get(user.id, conversation_id)
    return ChatConversationSchema.from_conversation(conversation)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorSchema}, 404: {"model": ErrorSchema}},
)
async def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    history: ChatHistoryService = Depends(get_chat_history_service),
) -> Response:
    await history.delete(user.id, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    receive = asyncio.create_task(websocket.receive_text())
    reply: asyncio.Task[ChatAnswerSchema] | None = None
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
    reply: asyncio.Task[ChatAnswerSchema] | None,
    ip: str | None,
    embedder: EmbeddingModel,
    generator: OllamaGenerator,
) -> asyncio.Task[ChatAnswerSchema] | None:
    try:
        incoming = IncomingMessage.validate_json(raw)
    except ValidationError as exc:
        await websocket.send_json(
            ChatSocketErrorSchema(
                type="error",
                code="invalid",
                message=t(validation_message(exc.errors(), with_field=False)),
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
                message=t("A reply is already in progress."),
            ).model_dump()
        )
        return reply
    try:
        request_id = await start_chat_request(user_id)
    except AppError as exc:
        await websocket.send_json(
            ChatSocketErrorSchema(type="error", code=exc.code, message=t(exc.message)).model_dump()
        )
        return None
    return asyncio.create_task(
        _answer(request_id, websocket, user_id, incoming, ip, embedder, generator)
    )


async def _answer(request_id: int, *args) -> ChatAnswerSchema:
    """The answer, with the user's chat slot freed however it ends
    (done, failed, cancelled, socket closed)."""
    try:
        return await _generate(*args)
    finally:
        await asyncio.shield(finish_chat_request(request_id))


async def _generate(
    websocket: WebSocket,
    user_id: int,
    ask: ChatAskSchema,
    ip: str | None,
    embedder: EmbeddingModel,
    generator: OllamaGenerator,
) -> ChatAnswerSchema:
    async with AsyncSessionLocal() as session:
        service = ChatService(session, embedder, generator)
        history = ChatHistoryService(session)
        question = ask.messages[-1].content
        # Saved before answering: the question is kept even if the answer
        # fails or is cancelled.
        conversation = await history.open_or_start(user_id, ask.conversation_id, question)
        await history.add_message(conversation, "user", question)
        await session.commit()

        async def send_delta(piece: str) -> None:
            await websocket.send_json(
                ChatDeltaSchema(type="delta", content=piece).model_dump()
            )

        content, documents = await service.reply(user_id, ask.messages, send_delta)
        sources = [
            ChatSourceSchema(id=int(d["document_id"]), name=str(d["name"]), filename=str(d["filename"]))
            for d in documents
        ]
        await history.add_message(
            conversation, "assistant", content, [source.model_dump() for source in sources]
        )
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
        return ChatAnswerSchema(
            type="answer",
            content=content,
            conversation_id=conversation.id,
            sources=sources,
        )


async def _finish_reply(
    websocket: WebSocket, reply: asyncio.Task[ChatAnswerSchema]
) -> None:
    try:
        answer = reply.result()
    except asyncio.CancelledError:
        return
    except AppError as exc:
        await websocket.send_json(
            ChatSocketErrorSchema(
                type="error",
                code=exc.code,
                message=t(exc.message),
            ).model_dump()
        )
        return
    await websocket.send_json(answer.model_dump())
