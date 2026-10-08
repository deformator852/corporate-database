from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_permission
from database import get_db
from models.user import User
from schemas.error import error_responses
from schemas.system import ReindexSchema
from services.search.index_model import reindex_progress
from services.system import system_status

router = APIRouter(
    prefix="/system",
    tags=["system"],
)


@router.get(
    "/reindex",
    response_model=ReindexSchema,
    responses=error_responses(401),
)
async def get_reindex_progress(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> ReindexSchema:
    """Every user's banner: whether search is being rebuilt for a new
    embedding model. A percentage, not counts: those would tell how many
    documents exist above the user's clearance."""
    progress = await reindex_progress(session)
    return ReindexSchema(active=progress.active, percent=progress.percent)


@router.get(
    "/status",
    responses=error_responses(401, 403),
    dependencies=[Depends(require_permission("system.view"))],
)
async def get_system_status(session: AsyncSession = Depends(get_db, scope="function")) -> dict[str, Any]:
    return await system_status(session)
