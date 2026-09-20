from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from exceptions import AppError
from models.rbac.role import Role
from models.user import User
from schemas.auth import UserLoginSchema
from services.password import verify_password

_USER_WITH_PERMISSIONS = selectinload(User.roles).selectinload(Role.permissions)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def authenticate(self, data: UserLoginSchema) -> User:
        user = await self.session.scalar(
            select(User)
            .where(User.email == data.email)
            .options(_USER_WITH_PERMISSIONS)
        )
        if user is None or not verify_password(data.password, user.password):
            raise AppError(
                "invalid_credentials",
                "Email or password is wrong",
                status_code=401,
            )
        return user

    async def get_with_permissions(self, user_id: int) -> User | None:
        return await self.session.scalar(
            select(User).where(User.id == user_id).options(_USER_WITH_PERMISSIONS)
        )
