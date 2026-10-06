from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Query,
    Response,
    WebSocket,
    status,
)

from api.deps import (
    get_audit_service,
    get_current_user,
    get_document_service,
    require_permission,
)
from api.ws import hold
from database import AsyncSessionLocal
from models.audit import AuditAction
from models.document import Document
from models.user import User
from schemas.document import (
    DocumentListItemSchema,
    DocumentListResponseSchema,
    DocumentUploadResponseSchema,
    DocumentUploadSchema,
)
from schemas.error import error_responses
from security import get_ws_payload
from services.audit import AuditService
from services.documents.access import event_classifications
from services.documents.document import DocumentService
from services.documents.hub import hub

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


@router.get(
    "",
    response_model=DocumentListResponseSchema,
    responses=error_responses(401, 403),
)
async def list_documents(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(require_permission("documents.list")),
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponseSchema:
    documents, total = await service.list_documents(user.id, page=page, per_page=per_page)
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
    responses=error_responses(400, 401, 403, 503),
)
async def upload_document(
    payload: Annotated[DocumentUploadSchema, Form()],
    user: User = Depends(require_permission("documents.create")),
    service: DocumentService = Depends(get_document_service),
    audit: AuditService = Depends(get_audit_service),
) -> DocumentUploadResponseSchema:
    document, converted = await service.accept_upload(payload, user.id)
    _audit(audit, AuditAction.DOCUMENT_UPLOAD, user, document)
    item = DocumentListItemSchema.from_document(document)
    return DocumentUploadResponseSchema(**item.model_dump(), converted=converted)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 503),
)
async def delete_document(
    document_id: int,
    user: User = Depends(require_permission("documents.delete")),
    service: DocumentService = Depends(get_document_service),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    document = await service.delete_document(document_id, user.id)
    _audit(audit, AuditAction.DOCUMENT_DELETE, user, document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _audit(audit: AuditService, action: AuditAction, user: User, document: Document) -> None:
    audit.record(
        action,
        actor=user,
        target_type="document",
        target_id=document.id,
        target_label=document.name,
        details={"filename": document.filename, "classification": document.classification},
    )


# Opened in the browser; everything else downloads. Never HTML, SVG or XML
# inline: those can run script.
_INLINE_TYPES = frozenset({"application/pdf", "text/plain", "text/markdown", "text/csv"})


@router.get(
    "/{document_id}/file",
    responses=error_responses(401, 403, 404),
)
async def open_document_file(
    document_id: int,
    user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    document, content = await service.open_file(document_id, user.id)
    _audit(audit, AuditAction.DOCUMENT_VIEW, user, document)
    disposition = "inline" if document.content_type in _INLINE_TYPES else "attachment"
    return Response(
        content=content,
        media_type=document.content_type,
        headers={
            "Content-Disposition": (f"{disposition}; filename*=UTF-8''{quote(document.filename)}"),
            # A file that sneaks in script cannot run it in the app's origin.
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "Cache-Control": "no-store",
        },
    )


@router.websocket("/ws")
async def document_events(
    websocket: WebSocket,
    payload=Depends(get_ws_payload),
) -> None:
    try:
        user_id = int(payload.sub)
    except TypeError, ValueError:
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
    async with AsyncSessionLocal() as session:
        return await event_classifications(session, user_id)
