from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.auth_service import AuthService


def get_auth_service(session: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(session)
