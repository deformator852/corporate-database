from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status

from api.deps import get_audit_service, get_role_service, require_permission
from models.audit import AuditAction
from models.rbac.role import Role
from models.user import User
from schemas.error import error_responses
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


@router.get(
    "",
    response_model=RoleListResponseSchema,
    responses=error_responses(401, 403),
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
    responses=error_responses(401, 403, 409),
)
async def create_role(
    payload: RoleCreateSchema,
    actor: User = Depends(require_permission("roles.create")),
    service: RoleService = Depends(get_role_service),
    audit: AuditService = Depends(get_audit_service),
) -> RoleListItemSchema:
    role = await service.create_role(payload, actor_id=actor.id)
    _audit(audit, AuditAction.ROLE_CREATE, actor, role, {"permissions": sorted(p.name for p in role.permissions)})
    return RoleListItemSchema.from_role(role)


@router.patch(
    "/{key}",
    response_model=RoleListItemSchema,
    responses=error_responses(401, 403, 404, 409),
)
async def update_role(
    key: str,
    payload: RoleWriteSchema,
    actor: User = Depends(require_permission("roles.update")),
    service: RoleService = Depends(get_role_service),
    audit: AuditService = Depends(get_audit_service),
) -> RoleListItemSchema:
    role = await service.update_role(key, payload, actor_id=actor.id)
    _audit(audit, AuditAction.ROLE_UPDATE, actor, role, {"permissions": sorted(p.name for p in role.permissions)})
    return RoleListItemSchema.from_role(role)


@router.delete(
    "/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
)
async def delete_role(
    key: str,
    actor: User = Depends(require_permission("roles.delete")),
    service: RoleService = Depends(get_role_service),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    role = await service.delete_role(key, actor_id=actor.id)
    _audit(audit, AuditAction.ROLE_DELETE, actor, role)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _audit(
    audit: AuditService, action: AuditAction, actor: User, role: Role, details: dict[str, Any] | None = None
) -> None:
    audit.record(action, actor=actor, target_type="role", target_id=role.key, target_label=role.name, details=details)
