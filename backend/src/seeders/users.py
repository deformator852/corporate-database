from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from services.password import hash_password

SEED_PASSWORD = "password"


async def seed_users(session: AsyncSession) -> None:
    exists = await session.scalar(select(User.id).limit(1))
    if exists is not None:
        return

    session.add_all(
        [
            User(
                first_name="John",
                last_name="Doe",
                email="admin@local.test",
                password=hash_password(SEED_PASSWORD),
            ),
            User(
                first_name="Michael",
                last_name="Keel",
                email="dev@local.test",
                password=hash_password(SEED_PASSWORD),
            ),
        ]
    )
