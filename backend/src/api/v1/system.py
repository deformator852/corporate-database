from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from database import get_db
from schemas.error import ErrorSchema
from services.system import system_status

router = APIRouter(
    prefix="/system",
    tags=["system"],
)


@router.get(
    "/status",
    responses={401: {"model": ErrorSchema}, 403: {"model": ErrorSchema}},
    dependencies=[Depends(require_permission("system.view"))],
)
async def get_system_status(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await system_status(session)
