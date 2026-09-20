from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.rbac.permission import Permission


class PermissionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_permissions(
        self, page: int = 1, per_page: int = 20
    ) -> tuple[list[Permission], int]:
        total = await self.session.scalar(select(func.count()).select_from(Permission))
        permissions = await self.session.scalars(
            select(Permission)
            .options(selectinload(Permission.roles))
            .order_by(Permission.name, Permission.key)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(permissions), total or 0
