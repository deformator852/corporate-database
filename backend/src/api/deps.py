from collections.abc import Callable

from authx.schema import TokenPayload
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from exceptions import AppError
from models import Permission, Role
from models.rbac import role_permissions, role_users
from models.user import User
from security import security, user_session_valid
from services.audit import AuditService
from services.auth import AuthService
from services.chat_history import ChatHistoryService
from services.documents.document import DocumentService
from services.notifications.notification import NotificationService
from services.permission import PermissionService
from services.role import RoleService
from services.storage import ObjectStorage
from services.user import UserService


def get_user_service(session: AsyncSession = Depends(get_db, scope="function")) -> UserService:
    return UserService(session)


def get_role_service(session: AsyncSession = Depends(get_db, scope="function")) -> RoleService:
    return RoleService(session)


def get_permission_service(
    session: AsyncSession = Depends(get_db, scope="function"),
) -> PermissionService:
    return PermissionService(session)


def get_audit_service(
    request: Request, session: AsyncSession = Depends(get_db, scope="function")
) -> AuditService:
    return AuditService(session, request.client.host if request.client else None)


def get_auth_service(
    session: AsyncSession = Depends(get_db, scope="function"),
    audit: AuditService = Depends(get_audit_service),
) -> AuthService:
    return AuthService(session, audit)


def get_notification_service(
    session: AsyncSession = Depends(get_db, scope="function"),
) -> NotificationService:
    return NotificationService(session)


def get_chat_history_service(
    session: AsyncSession = Depends(get_db, scope="function"),
) -> ChatHistoryService:
    return ChatHistoryService(session)


def get_storage() -> ObjectStorage:
    return ObjectStorage()


def get_document_service(
    session: AsyncSession = Depends(get_db, scope="function"),
    storage: ObjectStorage = Depends(get_storage),
) -> DocumentService:
    return DocumentService(session, storage)


async def get_current_user(
    payload: TokenPayload = Depends(security.access_token_required),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> User:
    try:
        user_id = int(payload.sub)
    except (TypeError, ValueError) as exc:
        raise AppError("unauthorized", "Not authenticated", status_code=401) from exc

    user = await session.get(User, user_id)
    if not user_session_valid(user, payload):
        raise AppError("unauthorized", "Not authenticated", status_code=401)
    return user


def require_permission(*keys) -> Callable:
    async def checker(
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db, scope="function"),
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
        session: AsyncSession = Depends(get_db, scope="function"),
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
