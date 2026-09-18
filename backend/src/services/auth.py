from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.user import User
from schemas.auth import UserLoginSchema
from services.password import verify_password


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def authenticate(self, data: UserLoginSchema) -> User:
        user = await self.session.scalar(select(User).where(User.email == data.email))
        if user is None or not verify_password(data.password, user.password):
            raise AppError(
                "invalid_credentials",
                "Email or password is wrong",
                status_code=401,
            )
        return user
