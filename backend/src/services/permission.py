from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.rbac.permission import Permission


class PermissionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_permissions(
        self, page: int = 1, per_page: int = 20, q: str = ""
    ) -> tuple[list[Permission], int]:
        filters = _permission_search_filters(q)
        count_query = select(func.count()).select_from(Permission)
        list_query = select(Permission).options(selectinload(Permission.roles))
        if filters:
            count_query = count_query.where(*filters)
            list_query = list_query.where(*filters)
        total = await self.session.scalar(count_query)
        permissions = await self.session.scalars(
            list_query.order_by(Permission.name, Permission.key)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(permissions), total or 0


def _permission_search_filters(q: str) -> list:
    term = q.strip()
    if not term:
        return []
    escaped = (
        term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    pattern = f"%{escaped}%"
    return [
        or_(
            Permission.name.ilike(pattern, escape="\\"),
            Permission.key.ilike(pattern, escape="\\"),
        )
    ]
