import asyncio
import logging
from collections.abc import Coroutine
from typing import Annotated, Any

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
from sqlalchemy import select

from api.deps import (
    get_audit_service,
    get_chat_history_service,
    get_chat_review_service,
    get_current_user,
    get_feedback_service,
    require_permission,
)
from api.ws import RECHECK_SECONDS, seconds_left, still_allowed
from database import AsyncSessionLocal
from exceptions import AppError
from i18n import t, use_language
from models.audit import AuditAction
from models.user import User
from schemas.chat import (
    RATING_VALUES,
    ChatAnswerSchema,
    ChatAskSchema,
    ChatCancelledSchema,
    ChatCancelSchema,
    ChatConversationListSchema,
    ChatConversationSchema,
    ChatDeltaSchema,
    ChatFeedbackListSchema,
    ChatPurgedSchema,
    ChatPurgeSchema,
    ChatRatingSchema,
    ChatReviewConversationSchema,
    ChatReviewListSchema,
    ChatSocketErrorSchema,
    ChatSourceSchema,
    ChatStartedSchema,
    ChatUserSchema,
    Rating,
)
from schemas.error import error_responses, validation_message
from security import get_ws_payload
from services.audit import AuditService
from services.chat.feedback import FeedbackService
from services.chat.generator import OllamaGenerator
from services.chat.history import ChatHistoryService
from services.chat.limit import finish_chat_request, start_chat_request
from services.chat.review import ChatPeriod, ChatReviewService
from services.chat.turn import answer_question
from services.search.embedding import EmbeddingModel, get_embedding_model

logger = logging.getLogger(__name__)
# Answers still being written after their client left (tab closed, network
# lost); kept referenced until done so they are not garbage-collected.
_DETACHED: set[asyncio.Task] = set()

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


@router.get(
    "/conversations",
    response_model=ChatConversationListSchema,
    responses=error_responses(401),
)
async def list_conversations(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
    q: Annotated[str, Query(max_length=100)] = "",
    user: User = Depends(get_current_user),
    history: ChatHistoryService = Depends(get_chat_history_service),
) -> ChatConversationListSchema:
    """The user's own chats; `q` finds those whose title or messages hold it."""
    if q.strip():
        items, total = await history.search_conversations(user.id, q, page=page, per_page=per_page)
    else:
        items, total = await history.list_conversations(user.id, page=page, per_page=per_page)
    return ChatConversationListSchema.from_page(items, page=page, per_page=per_page, total=total)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ChatConversationSchema,
    responses=error_responses(401, 404),
)
async def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    history: ChatHistoryService = Depends(get_chat_history_service),
) -> ChatConversationSchema:
    conversation = await history.get(user.id, conversation_id)
    return ChatConversationSchema.from_conversation(conversation)


@router.get(
    "/review/conversations",
    response_model=ChatReviewListSchema,
    responses=error_responses(401, 403),
)
async def review_conversations(
    user_id: Annotated[int | None, Query(ge=1)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    actor: User = Depends(require_permission("chat.history")),
    review: ChatReviewService = Depends(get_chat_review_service),
) -> ChatReviewListSchema:
    """Every reachable user's chats, or one user's."""
    items, total = await review.list_conversations(actor.id, user_id, page, per_page)
    return ChatReviewListSchema.from_page(items, page=page, per_page=per_page, total=total)


@router.get(
    "/review/conversations/{conversation_id}",
    response_model=ChatReviewConversationSchema,
    responses=error_responses(401, 403, 404),
)
async def review_conversation(
    conversation_id: int,
    actor: User = Depends(require_permission("chat.history")),
    review: ChatReviewService = Depends(get_chat_review_service),
    audit: AuditService = Depends(get_audit_service),
) -> ChatReviewConversationSchema:
    found = await review.get(actor.id, conversation_id)
    # Whose chat was read; never its title, which is the first question.
    audit.record(
        AuditAction.CHAT_VIEW,
        actor=actor,
        target_type="user",
        target_id=found.user.id,
        target_label=found.user.email,
        details={"conversation_id": conversation_id},
    )
    return ChatReviewConversationSchema(
        **ChatConversationSchema.from_conversation(found.conversation).model_dump(),
        user=ChatUserSchema.from_user(found.user),
    )


@router.post(
    "/review/purge",
    response_model=ChatPurgedSchema,
    responses=error_responses(400, 401, 403, 404),
)
async def purge_conversations(
    payload: ChatPurgeSchema,
    actor: User = Depends(require_permission("chat.purge")),
    review: ChatReviewService = Depends(get_chat_review_service),
    audit: AuditService = Depends(get_audit_service),
) -> ChatPurgedSchema:
    """Deletes chats last active in the period: one user's or every reachable one's."""
    deleted = await review.purge(actor.id, payload.user_id, ChatPeriod(payload.since, payload.until))
    audit.record(
        AuditAction.CHAT_PURGE,
        actor=actor,
        target_type="user" if payload.user_id else None,
        target_id=payload.user_id,
        details={
            "since": payload.since.isoformat() if payload.since else None,
            "until": payload.until.isoformat() if payload.until else None,
            "deleted": deleted,
        },
    )
    return ChatPurgedSchema(deleted=deleted)


@router.put(
    "/conversations/{conversation_id}/messages/{message_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 404),
)
async def rate_answer(
    conversation_id: int,
    message_id: int,
    payload: ChatRatingSchema,
    user: User = Depends(get_current_user),
    feedback: FeedbackService = Depends(get_feedback_service),
) -> Response:
    rating = RATING_VALUES[payload.rating] if payload.rating else None
    await feedback.rate(user.id, conversation_id, message_id, rating)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/feedback",
    response_model=ChatFeedbackListSchema,
    responses=error_responses(401, 403),
)
async def list_feedback(
    rating: Rating = "down",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    _user: User = Depends(require_permission("chat.feedback")),
    feedback: FeedbackService = Depends(get_feedback_service),
) -> ChatFeedbackListSchema:
    items, total = await feedback.rated(RATING_VALUES[rating], page, per_page)
    return ChatFeedbackListSchema.from_page(items, page=page, per_page=per_page, total=total)


IncomingMessage = TypeAdapter(Annotated[ChatAskSchema | ChatCancelSchema, Field(discriminator="type")])


@router.websocket("/ws")
async def chat_socket(
    websocket: WebSocket,
    payload=Depends(get_ws_payload),
) -> None:
    try:
        user_id = int(payload.sub)
    except TypeError, ValueError:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    ip = websocket.client.host if websocket.client else None
    embedder = get_embedding_model()
    generator = OllamaGenerator()
    receive = asyncio.create_task(websocket.receive_text())
    reply: asyncio.Task[ChatAnswerSchema] | None = None
    # The client went away, as opposed to the session ending or Stop.
    left = False
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
                    left = True
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
        left = True
        return
    finally:
        receive.cancel()
        if reply is not None and not reply.done():
            if left:
                # Finish and save the answer: it shows in the chat history
                # when the user comes back.
                _detach(reply)
            else:
                reply.cancel()
                try:
                    await reply
                except asyncio.CancelledError, AppError:
                    pass


def _detach(reply: asyncio.Task[ChatAnswerSchema]) -> None:
    _DETACHED.add(reply)

    def done(task: asyncio.Task[ChatAnswerSchema]) -> None:
        _DETACHED.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning("Chat answer after the client left failed", exc_info=task.exception())

    reply.add_done_callback(done)


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
    # Read per message: the user may switch languages with the socket open.
    async with AsyncSessionLocal() as session:
        use_language(await session.scalar(select(User.language).where(User.id == user_id)))
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
        except asyncio.CancelledError, AppError:
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
            ChatSocketErrorSchema(type="error", code=exc.code, message=t(exc.message, **exc.params)).model_dump()
        )
        return None
    return asyncio.create_task(_answer(request_id, _generate(websocket, user_id, incoming, ip, embedder, generator)))


async def _answer(request_id: int, answer: Coroutine[Any, Any, ChatAnswerSchema]) -> ChatAnswerSchema:
    """`answer`, with the user's chat slot freed however it ends (done,
    failed, cancelled, socket closed)."""
    try:
        return await answer
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
    client_gone = False

    async def send(message: dict[str, object]) -> None:
        # After the client left, the answer is still written and saved.
        nonlocal client_gone
        if client_gone:
            return
        try:
            await websocket.send_json(message)
        except Exception:  # noqa: BLE001 - the server and test client raise
            # different errors on a closed socket; any of them means gone.
            client_gone = True

    async def send_delta(piece: str) -> None:
        await send(ChatDeltaSchema(type="delta", content=piece).model_dump())

    async def send_started(conversation_id: int) -> None:
        await send(ChatStartedSchema(type="started", conversation_id=conversation_id).model_dump())

    turn = await answer_question(
        user_id,
        ask,
        ip=ip,
        embedder=embedder,
        generator=generator,
        on_delta=send_delta,
        on_started=send_started,
    )
    return ChatAnswerSchema(
        type="answer",
        content=turn.content,
        conversation_id=turn.conversation_id,
        message_id=turn.message_id,
        sources=[ChatSourceSchema(**source) for source in turn.sources],
    )


async def _finish_reply(websocket: WebSocket, reply: asyncio.Task[ChatAnswerSchema]) -> None:
    try:
        answer = reply.result()
    except asyncio.CancelledError:
        return
    except AppError as exc:
        await websocket.send_json(
            ChatSocketErrorSchema(
                type="error",
                code=exc.code,
                message=t(exc.message, **exc.params),
            ).model_dump()
        )
        return
    await websocket.send_json(answer.model_dump())
