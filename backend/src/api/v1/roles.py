from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from api.deps import get_audit_service, get_role_service, require_permission
from models.audit import AuditAction
from models.user import User
from schemas.error import ErrorSchema
from schemas.role import (
    RoleCreateSchema,
    RoleListItemSchema,
    RoleListResponseSchema,
    RoleWriteSchema,
)
from services.audit import AuditService
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
    "",
    response_model=RoleListResponseSchema,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_permission("roles.list"))],
)
async def list_roles(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str, Query(max_length=100)] = "",
    service: RoleService = Depends(get_role_service),
) -> RoleListResponseSchema:
    roles, total = await service.list_roles(page=page, per_page=per_page, q=q)
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
)
async def create_role(
    payload: RoleCreateSchema,
    actor: User = Depends(require_permission("roles.create")),
    service: RoleService = Depends(get_role_service),
    audit: AuditService = Depends(get_audit_service),
) -> RoleListItemSchema:
    role = await service.create_role(payload, actor_id=actor.id)
    audit.record(
        AuditAction.ROLE_CREATE,
        actor=actor,
        target_type="role",
        target_id=role.key,
        target_label=role.name,
        details={"permissions": sorted(p.key for p in role.permissions)},
    )
    return RoleListItemSchema.from_role(role)


@router.patch(
    "/{key}",
    response_model=RoleListItemSchema,
    responses={
        **ERROR_RESPONSES,
        404: {"model": ErrorSchema},
        409: {"model": ErrorSchema},
    },
)
async def update_role(
    key: str,
    payload: RoleWriteSchema,
    actor: User = Depends(require_permission("roles.update")),
    service: RoleService = Depends(get_role_service),
    audit: AuditService = Depends(get_audit_service),
) -> RoleListItemSchema:
    role = await service.update_role(key, payload, actor_id=actor.id)
    audit.record(
        AuditAction.ROLE_UPDATE,
        actor=actor,
        target_type="role",
        target_id=role.key,
        target_label=role.name,
        details={"permissions": sorted(p.key for p in role.permissions)},
    )
    return RoleListItemSchema.from_role(role)


@router.delete(
    "/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **ERROR_RESPONSES,
        404: {"model": ErrorSchema},
        409: {"model": ErrorSchema},
    },
)
async def delete_role(
    key: str,
    actor: User = Depends(require_permission("roles.delete")),
    service: RoleService = Depends(get_role_service),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    role = await service.delete_role(key, actor_id=actor.id)
    audit.record(
        AuditAction.ROLE_DELETE,
        actor=actor,
        target_type="role",
        target_id=key,
        target_label=role.name,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
