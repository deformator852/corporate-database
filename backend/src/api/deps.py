from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from authx.schema import TokenPayload
from database import get_db
from exceptions import AppError
from models.user import User
from security import security
from services.auth import AuthService


def get_auth_service(session: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(session)


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
