from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_audit_service, require_permission
from api.ws import hold
from database import get_db
from exceptions import AppError
from models.audit import AuditAction
from models.document import DONE_STATUSES, Document
from models.user import User
from schemas.error import error_responses
from schemas.error_log import ErrorCategory, ErrorLevel, ErrorLogListSchema
from security import get_ws_payload
from services.audit import AuditService
from services.documents.document import CeleryDocumentQueue
from services.documents.rechunk import mark_outdated
from services.error_log import ErrorLogService
from services.search.index_model import outdated_index_model, rebuild_index
from services.search.reindex_hub import reindex_hub
from services.system import system_status
from settings import embedding_model_key

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
    category: ErrorCategory | None = None,
    session: AsyncSession = Depends(get_db, scope="function"),
) -> ErrorLogListSchema:
    """Warnings and errors of the backend and the worker, newest first."""
    entries, total = await ErrorLogService(session).list_entries(page, per_page, level, category)
    return ErrorLogListSchema.from_page(entries, page=page, per_page=per_page, total=total)


@router.get(
    "/status",
    responses=error_responses(401, 403),
    dependencies=[Depends(require_permission("system.view"))],
)
async def get_system_status(session: AsyncSession = Depends(get_db, scope="function")) -> dict[str, Any]:
    return await system_status(session)


@router.post(
    "/rechunk",
    responses=error_responses(401, 403, 409),
)
async def rechunk_documents(
    user: User = Depends(require_permission("system.rechunk")),
    session: AsyncSession = Depends(get_db, scope="function"),
    audit: AuditService = Depends(get_audit_service),
) -> dict[str, int]:
    """Re-chunks the documents cut with another chunk size or overlap; they
    stay searchable meanwhile. Returns how many were marked."""
    marked = await mark_outdated(session)
    audit.record(AuditAction.SYSTEM_RECHUNK, actor=user, details={"documents": marked})
    await session.commit()
    if marked:
        CeleryDocumentQueue().start_rechunk()
        await reindex_hub.refresh()
    return {"documents": marked}


@router.post(
    "/reindex",
    responses=error_responses(401, 403, 409),
)
async def reindex_documents(
    user: User = Depends(require_permission("system.rechunk")),
    session: AsyncSession = Depends(get_db, scope="function"),
    audit: AuditService = Depends(get_audit_service),
) -> dict[str, int]:
    """After EMBEDDING_MODEL changed: embeds every document again with it.
    Search finds each document again once it is done. Returns how many were
    queued."""
    previous = await outdated_index_model(session)
    if previous is None:
        raise AppError(
            "conflict", "The search index is already built with the current embedding model.", status_code=409
        )
    model = embedding_model_key()
    queued = await rebuild_index(session, model)
    audit.record(AuditAction.SYSTEM_REINDEX, actor=user, details={"from": previous, "to": model, "documents": queued})
    await session.commit()
    queue = CeleryDocumentQueue()
    # Every unfinished one: those uploaded while the index was outdated too.
    for document_id in await session.scalars(select(Document.id).where(Document.status.not_in(DONE_STATUSES))):
        queue.enqueue(document_id)
    await reindex_hub.refresh()
    return {"documents": queued}
