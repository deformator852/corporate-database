from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Query,
    Response,
    WebSocket,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_audit_service, get_document_service, require_permission
from api.ws import hold
from database import AsyncSessionLocal
from models.audit import AuditAction
from models.rbac import role_permissions, role_users
from models.rbac.permission import Permission
from models.user import User
from schemas.document import (
    DocumentListItemSchema,
    DocumentListResponseSchema,
    DocumentUploadResponseSchema,
    DocumentUploadSchema,
)
from schemas.error import ErrorSchema
from security import get_ws_payload
from services.audit import AuditService
from services.documents.document import DocumentService
from services.documents.access import classifications_for_user
from services.documents.hub import hub

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)

ERROR_RESPONSES = {
    401: {"model": ErrorSchema},
    403: {"model": ErrorSchema},
}


@router.get(
    "",
    response_model=DocumentListResponseSchema,
    responses=ERROR_RESPONSES,
)
async def list_documents(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(require_permission("documents.list")),
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponseSchema:
    documents, total = await service.list_documents(
        user.id, page=page, per_page=per_page
    )
    return DocumentListResponseSchema.from_page(
        documents,
        page=page,
        per_page=per_page,
        total=total,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentUploadResponseSchema,
    responses={
        **ERROR_RESPONSES,
        400: {"model": ErrorSchema},
        503: {"model": ErrorSchema},
    },
)
async def upload_document(
    payload: Annotated[DocumentUploadSchema, Form()],
    user: User = Depends(require_permission("documents.create")),
    service: DocumentService = Depends(get_document_service),
    audit: AuditService = Depends(get_audit_service),
) -> DocumentUploadResponseSchema:
    document, converted = await service.accept_upload(payload, user.id)
    audit.record(
        AuditAction.DOCUMENT_UPLOAD,
        actor=user,
        target_type="document",
        target_id=document.id,
        target_label=document.name,
        details={
            "filename": document.filename,
            "classification": document.classification,
        },
    )
    item = DocumentListItemSchema.from_document(document)
    return DocumentUploadResponseSchema(**item.model_dump(), converted=converted)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **ERROR_RESPONSES,
        404: {"model": ErrorSchema},
        503: {"model": ErrorSchema},
    },
)
async def delete_document(
    document_id: int,
    user: User = Depends(require_permission("documents.delete")),
    service: DocumentService = Depends(get_document_service),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    document = await service.delete_document(document_id, user.id)
    audit.record(
        AuditAction.DOCUMENT_DELETE,
        actor=user,
        target_type="document",
        target_id=document_id,
        target_label=document.name,
        details={
            "filename": document.filename,
            "classification": document.classification,
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.websocket("/ws")
async def document_events(
    websocket: WebSocket,
    payload=Depends(get_ws_payload),
) -> None:
    try:
        user_id = int(payload.sub)
    except (TypeError, ValueError):
        await websocket.close(code=4401)
        return
    classifications = await _event_classifications(user_id)
    if classifications is None:
        await websocket.close(code=4403)
        return
    await hub.connect(websocket, classifications)

    async def recheck() -> bool:
        # Permissions may change while the socket is open.
        current = await _event_classifications(user_id)
        if current is None:
            return False
        hub.update(websocket, current)
        return True

    try:
        await hold(websocket, payload, recheck)
    finally:
        hub.disconnect(websocket)


async def _event_classifications(user_id: int) -> tuple[str, ...] | None:
    """Classifications whose events the user may receive; None without access."""
    async with AsyncSessionLocal() as session:
        if not await _can_list_documents(session, user_id):
            return None
        return await classifications_for_user(session, user_id)


async def _can_list_documents(session: AsyncSession, user_id: int) -> bool:
    found = await session.scalar(
        select(Permission.id)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(role_users, role_users.c.role_id == role_permissions.c.role_id)
        .where(
            role_users.c.user_id == user_id,
            Permission.key == "documents.list",
        )
        .limit(1)
    )
    return found is not None
