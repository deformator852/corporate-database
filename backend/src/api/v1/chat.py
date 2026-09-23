from fastapi import APIRouter, Depends

from api.deps import get_chat_service, get_current_user
from models.user import User
from schemas.chat import ChatRequestSchema, ChatResponseSchema
from schemas.error import ErrorSchema
from services.chat import ChatService

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)

ERROR_RESPONSES = {
    401: {"model": ErrorSchema},
    403: {"model": ErrorSchema},
    503: {"model": ErrorSchema},
}


@router.post(
    "",
    response_model=ChatResponseSchema,
    responses=ERROR_RESPONSES,
)
async def send_chat_message(
    payload: ChatRequestSchema,
    user: User = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponseSchema:
    content = await service.reply(user.id, payload.messages)
    return ChatResponseSchema(content=content)
