import asyncio

from database import AsyncSessionLocal
from seeders.permissions import seed_permissions
from seeders.roles import seed_roles
from seeders.users import seed_users


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed_permissions(session)
        await seed_roles(session)
        await seed_users(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
