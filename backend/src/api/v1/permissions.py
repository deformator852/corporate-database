from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.deps import get_permission_service, require_permission
from schemas.error import error_responses
from schemas.permission import PermissionListResponseSchema
from services.permission import PermissionService

router = APIRouter(
    prefix="/permissions",
    tags=["permissions"],
)


@router.get(
    "",
    response_model=PermissionListResponseSchema,
    responses=error_responses(401, 403),
    dependencies=[Depends(require_permission("permissions.list"))],
)
async def list_permissions(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str, Query(max_length=100)] = "",
    service: PermissionService = Depends(get_permission_service),
) -> PermissionListResponseSchema:
    permissions, total = await service.list_permissions(
        page=page,
        per_page=per_page,
        q=q,
    )
    return PermissionListResponseSchema.from_page(
        permissions,
        page=page,
        per_page=per_page,
        total=total,
    )
