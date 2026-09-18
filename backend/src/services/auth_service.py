from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.user import User
from services.password_service import verify_password


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.session.scalar(select(User).where(User.email == email))
        if user is None or not verify_password(password, user.hashed_password):
            raise AppError(
                "invalid_credentials",
                "Email or password is wrong",
                status_code=401,
            )
        return user
