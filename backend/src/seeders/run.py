import asyncio

from database import AsyncSessionLocal
from seeders.users import seed_users


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed_users(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
