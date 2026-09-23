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

from api.deps import get_current_user, get_notification_service
from models.user import User
from schemas.error import ErrorSchema
from schemas.notification import (
    NotificationListResponseSchema,
    NotificationReadSchema,
)
from security import get_ws_payload
from services.notification import NotificationService
from services.notification_hub import hub

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
)

ERROR_RESPONSES = {
    401: {"model": ErrorSchema},
}


@router.get(
    "",
    response_model=NotificationListResponseSchema,
    responses=ERROR_RESPONSES,
)
async def list_notifications(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponseSchema:
    items, total, unread_count = await service.list_notifications(
        user.id,
        page=page,
        per_page=per_page,
    )
    return NotificationListResponseSchema.from_page(
        items,
        page=page,
        per_page=per_page,
        total=total,
        unread_count=unread_count,
    )


@router.post(
    "/read",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERROR_RESPONSES,
)
async def mark_notifications_read(
    payload: NotificationReadSchema,
    user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Response:
    await service.mark_read(user.id, payload.ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERROR_RESPONSES,
)
async def clear_notifications(
    user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Response:
    await service.clear(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.websocket("/ws")
async def notification_events(
    websocket: WebSocket,
    payload=Depends(get_ws_payload),
) -> None:
    try:
        user_id = int(payload.sub)
    except (TypeError, ValueError):
        await websocket.close(code=4401)
        return
    await hub.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(user_id, websocket)
