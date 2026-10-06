from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from database import get_db
from schemas.error import error_responses
from services.system import system_status

router = APIRouter(
    prefix="/system",
    tags=["system"],
)


@router.get(
    "/status",
    responses=error_responses(401, 403),
    dependencies=[Depends(require_permission("system.view"))],
)
async def get_system_status(session: AsyncSession = Depends(get_db, scope="function")) -> dict[str, Any]:
    return await system_status(session)
