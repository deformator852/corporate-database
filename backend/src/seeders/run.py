import asyncio

from database import AsyncSessionLocal
from seeders.permissions import seed_permissions
from seeders.qdrant import seed_qdrant
from seeders.roles import seed_roles


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed_permissions(session)
        await seed_roles(session)
        await seed_permissions(session)
        await session.commit()
    await seed_qdrant()


if __name__ == "__main__":
    asyncio.run(main())
