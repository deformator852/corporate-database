from collections.abc import Callable

from authx.schema import TokenPayload
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from exceptions import AppError
from models import Permission, Role
from models.rbac import role_permissions, role_users
from models.user import User
from security import security
from services.auth import AuthService
from services.document import DocumentService
from services.notification import NotificationService
from services.permission import PermissionService
from services.role import RoleService
from services.storage import ObjectStorage
from services.user import UserService


def get_user_service(session: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(session)


def get_role_service(session: AsyncSession = Depends(get_db)) -> RoleService:
    return RoleService(session)


def get_permission_service(
    session: AsyncSession = Depends(get_db),
) -> PermissionService:
    return PermissionService(session)


def get_auth_service(session: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(session)


def get_notification_service(
    session: AsyncSession = Depends(get_db),
) -> NotificationService:
    return NotificationService(session)


def get_storage() -> ObjectStorage:
    return ObjectStorage()


def get_document_service(
    session: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
) -> DocumentService:
    return DocumentService(session, storage)


async def get_current_user(
    payload: TokenPayload = Depends(security.access_token_required),
    session: AsyncSession = Depends(get_db),
) -> User:
    try:
        user_id = int(payload.sub)
    except (TypeError, ValueError) as exc:
        raise AppError("unauthorized", "Not authenticated", status_code=401) from exc

    user = await session.get(User, user_id)
    if user is None:
        raise AppError("unauthorized", "Not authenticated", status_code=401)
    return user


def require_permission(*keys) -> Callable:
    async def checker(
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ):
        found = await session.scalar(
            select(Permission.id)
            .join(role_permissions, role_permissions.c.permission_id == Permission.id)
            .join(role_users, role_users.c.role_id == role_permissions.c.role_id)
            .where(
                role_users.c.user_id == user.id,
                Permission.key.in_(keys),
            )
            .limit(1)
        )
        if found is None:
            raise AppError("forbidden", "Insufficient permissions", status_code=403)
        return user

    return checker


def require_role(*keys) -> Callable:
    async def checker(
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ) -> User:
        found = await session.scalar(
            select(Role.id)
            .join(role_users, role_users.c.role_id == Role.id)
            .where(
                role_users.c.user_id == user.id,
                Role.key.in_(keys),
            )
            .limit(1)
        )
        if found is None:
            raise AppError("forbidden", "Insufficient permissions", status_code=403)
        return user

    return checker
