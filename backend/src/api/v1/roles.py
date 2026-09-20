from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from api.deps import get_role_service, require_permission
from exceptions import AppError
from schemas.error_schema import ErrorSchema
from schemas.role import (
    PermissionOptionPageSchema,
    RoleCreateSchema,
    RoleListItemSchema,
    RoleListResponseSchema,
    RoleWriteSchema,
)
from services.role import RoleService

router = APIRouter(
    prefix="/roles",
    tags=["roles"],
)

ERROR_RESPONSES = {
    401: {"model": ErrorSchema},
    403: {"model": ErrorSchema},
}


@router.get(
    "/permissions",
    response_model=PermissionOptionPageSchema,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_permission("roles.create", "roles.update"))],
)
async def list_role_permissions(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str, Query(max_length=100)] = "",
    service: RoleService = Depends(get_role_service),
) -> PermissionOptionPageSchema:
    permissions, total = await service.list_permissions(
        page=page,
        per_page=per_page,
        q=q,
    )
    return PermissionOptionPageSchema.from_page(
        permissions,
        page=page,
        per_page=per_page,
        total=total,
    )


@router.get(
    "",
    response_model=RoleListResponseSchema,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_permission("roles.list"))],
)
async def get_roles(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    service: RoleService = Depends(get_role_service),
) -> RoleListResponseSchema:
    raise AppError("dsd", "asdd", 400)
    roles, total = await service.get_roles(page=page, per_page=per_page)
    return RoleListResponseSchema.from_page(
        roles,
        page=page,
        per_page=per_page,
        total=total,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RoleListItemSchema,
    responses={
        **ERROR_RESPONSES,
        409: {"model": ErrorSchema},
    },
    dependencies=[Depends(require_permission("roles.create"))],
)
async def create_role(
    payload: RoleCreateSchema,
    service: RoleService = Depends(get_role_service),
) -> RoleListItemSchema:
    role = await service.create_role(payload)
    return RoleListItemSchema.from_role(role)


@router.patch(
    "/{key}",
    response_model=RoleListItemSchema,
    responses={
        **ERROR_RESPONSES,
        404: {"model": ErrorSchema},
        409: {"model": ErrorSchema},
    },
    dependencies=[Depends(require_permission("roles.update"))],
)
async def update_role(
    key: str,
    payload: RoleWriteSchema,
    service: RoleService = Depends(get_role_service),
) -> RoleListItemSchema:
    role = await service.update_role(key, payload)
    return RoleListItemSchema.from_role(role)


@router.delete(
    "/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **ERROR_RESPONSES,
        404: {"model": ErrorSchema},
        409: {"model": ErrorSchema},
    },
    dependencies=[Depends(require_permission("roles.delete"))],
)
async def delete_role(
    key: str,
    service: RoleService = Depends(get_role_service),
) -> Response:
    await service.delete_role(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
