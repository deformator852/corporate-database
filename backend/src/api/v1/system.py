from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from api.ws import hold
from database import get_db
from schemas.error import error_responses
from schemas.error_log import ErrorLevel, ErrorLogListSchema, ErrorSource
from security import get_ws_payload
from services.error_log import ErrorLogService
from services.search.reindex_hub import reindex_hub
from services.system import system_status

router = APIRouter(
    prefix="/system",
    tags=["system"],
)


@router.websocket("/reindex/ws")
async def reindex_events(websocket: WebSocket, payload=Depends(get_ws_payload)) -> None:
    """Every signed-in user's banner: {active, percent} of an embedding model
    switch, now and at each change (services/search/reindex_hub.py)."""
    await reindex_hub.connect(websocket)
    try:
        await hold(websocket, payload)
    finally:
        reindex_hub.disconnect(websocket)


@router.get(
    "/errors",
    response_model=ErrorLogListSchema,
    responses=error_responses(401, 403),
    dependencies=[Depends(require_permission("system.errors"))],
)
async def list_errors(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 25,
    level: ErrorLevel | None = None,
    source: ErrorSource | None = None,
    session: AsyncSession = Depends(get_db, scope="function"),
) -> ErrorLogListSchema:
    """Warnings and errors of the backend and the worker, newest first."""
    entries, total = await ErrorLogService(session).list_entries(page, per_page, level, source)
    return ErrorLogListSchema.from_page(entries, page=page, per_page=per_page, total=total)


@router.get(
    "/status",
    responses=error_responses(401, 403),
    dependencies=[Depends(require_permission("system.view"))],
)
async def get_system_status(session: AsyncSession = Depends(get_db, scope="function")) -> dict[str, Any]:
    return await system_status(session)
