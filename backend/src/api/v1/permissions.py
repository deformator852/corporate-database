from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.deps import get_permission_service, require_permission
from schemas.error_schema import ErrorSchema
from schemas.permission import PermissionListResponseSchema
from services.permission import PermissionService

router = APIRouter(
    prefix="/permissions",
    tags=["permissions"],
)

ERROR_RESPONSES = {
    401: {"model": ErrorSchema},
    403: {"model": ErrorSchema},
}


@router.get(
    "",
    response_model=PermissionListResponseSchema,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_permission("permissions.list"))],
)
async def get_permissions(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    service: PermissionService = Depends(get_permission_service),
) -> PermissionListResponseSchema:
    permissions, total = await service.get_permissions(page=page, per_page=per_page)
    return PermissionListResponseSchema.from_page(
        permissions,
        page=page,
        per_page=per_page,
        total=total,
    )
