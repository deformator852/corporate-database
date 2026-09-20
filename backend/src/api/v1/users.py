from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from api.deps import get_user_service, require_permission
from models.user import User
from schemas.error import ErrorSchema
from schemas.user import (
    UserCreateSchema,
    UserListItemSchema,
    UserListResponseSchema,
    UserUpdateSchema,
)
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
    dependencies=[Depends(require_permission("users.create"))],
)
async def create_user(
    payload: UserCreateSchema,
    service: UserService = Depends(get_user_service),
) -> UserListItemSchema:
    user = await service.create_user(payload)
    return UserListItemSchema.from_user(user)


@router.patch(
    "/{user_id}",
    response_model=UserListItemSchema,
    responses={
        **ERROR_RESPONSES,
        404: {"model": ErrorSchema},
        409: {"model": ErrorSchema},
    },
    dependencies=[Depends(require_permission("users.update"))],
)
async def update_user(
    user_id: int,
    payload: UserUpdateSchema,
    service: UserService = Depends(get_user_service),
) -> UserListItemSchema:
    user = await service.update_user(user_id, payload)
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
) -> Response:
    await service.delete_user(user_id, actor_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
