from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from services.password_service import hash_password

SEED_PASSWORD = "password"


async def seed_users(session: AsyncSession) -> None:
    exists = await session.scalar(select(User.id).limit(1))
    if exists is not None:
        return

    session.add_all(
        [
            User(
                email="admin@local.test", hashed_password=hash_password(SEED_PASSWORD)
            ),
            User(email="dev@local.test", hashed_password=hash_password(SEED_PASSWORD)),
        ]
    )
