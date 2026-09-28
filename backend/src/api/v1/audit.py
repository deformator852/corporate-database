from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.deps import get_audit_service, require_permission
from schemas.audit import AuditListResponseSchema
from schemas.error import ErrorSchema
from services.audit import AuditService

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
)


@router.get(
    "",
    response_model=AuditListResponseSchema,
    responses={401: {"model": ErrorSchema}, 403: {"model": ErrorSchema}},
    dependencies=[Depends(require_permission("audit.list"))],
)
async def list_audit(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str, Query(max_length=100)] = "",
    action: Annotated[str, Query(max_length=64)] = "",
    service: AuditService = Depends(get_audit_service),
) -> AuditListResponseSchema:
    entries, total = await service.list_entries(
        page=page, per_page=per_page, q=q, action=action
    )
    return AuditListResponseSchema.from_page(
        entries, page=page, per_page=per_page, total=total
    )
