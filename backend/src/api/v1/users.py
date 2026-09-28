from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from api.deps import get_audit_service, get_user_service, require_permission
from models.audit import AuditAction
from models.user import User
from schemas.error import ErrorSchema
from schemas.user import (
    UserCreateSchema,
    UserListItemSchema,
    UserListResponseSchema,
    UserUpdateSchema,
)
from services.audit import AuditService
from services.user import UserService

router = APIRouter(
    prefix="/users",
    tags=["users"],
)

ERROR_RESPONSES = {
    401: {"model": ErrorSchema},
    403: {"model": ErrorSchema},
}


@router.get(
    "",
    response_model=UserListResponseSchema,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_permission("users.list"))],
)
async def list_users(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    service: UserService = Depends(get_user_service),
) -> UserListResponseSchema:
    users, total = await service.list_users(page=page, per_page=per_page)
    return UserListResponseSchema.from_page(
        users,
        page=page,
        per_page=per_page,
        total=total,
        admin_ids=await service.admin_ids(),
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=UserListItemSchema,
    responses={
        **ERROR_RESPONSES,
        409: {"model": ErrorSchema},
    },
)
async def create_user(
    payload: UserCreateSchema,
    actor: User = Depends(require_permission("users.create")),
    service: UserService = Depends(get_user_service),
    audit: AuditService = Depends(get_audit_service),
) -> UserListItemSchema:
    user = await service.create_user(payload, actor_id=actor.id)
    audit.record(
        AuditAction.USER_CREATE,
        actor=actor,
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details={"roles": [role.key for role in user.roles]},
    )
    return UserListItemSchema.from_user(user)


@router.patch(
    "/{user_id}",
    response_model=UserListItemSchema,
    responses={
        **ERROR_RESPONSES,
        404: {"model": ErrorSchema},
        409: {"model": ErrorSchema},
    },
)
async def update_user(
    user_id: int,
    payload: UserUpdateSchema,
    actor: User = Depends(require_permission("users.update")),
    service: UserService = Depends(get_user_service),
    audit: AuditService = Depends(get_audit_service),
) -> UserListItemSchema:
    user = await service.update_user(user_id, payload, actor_id=actor.id)
    audit.record(
        AuditAction.USER_UPDATE,
        actor=actor,
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details={
            "roles": [role.key for role in user.roles],
            "password_changed": payload.password is not None,
        },
    )
    return UserListItemSchema.from_user(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **ERROR_RESPONSES,
        404: {"model": ErrorSchema},
        409: {"model": ErrorSchema},
    },
)
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_permission("users.delete")),
    service: UserService = Depends(get_user_service),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    user = await service.delete_user(user_id, actor_id=current_user.id)
    audit.record(
        AuditAction.USER_DELETE,
        actor=current_user,
        target_type="user",
        target_id=user_id,
        target_label=user.email,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
