from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from exceptions import AppError
from models.rbac.constants import ADMIN_ROLE_KEY
from models.rbac.permission import Permission
from models.rbac.role import Role
from schemas.key import key_from_name
from schemas.role import RoleCreateSchema, RoleWriteSchema


class RoleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_roles(
        self, page: int = 1, per_page: int = 20
    ) -> tuple[list[Role], int]:
        total = await self.session.scalar(select(func.count()).select_from(Role))
        roles = await self.session.scalars(
            select(Role)
            .options(selectinload(Role.permissions))
            .order_by(Role.name, Role.key)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(roles), total or 0

    async def list_permissions(
        self,
        page: int = 1,
        per_page: int = 20,
        q: str = "",
    ) -> tuple[list[Permission], int]:
        filters = _permission_search_filters(q)
        count_query = select(func.count()).select_from(Permission)
        list_query = select(Permission)
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

    async def create_role(self, data: RoleCreateSchema) -> Role:
        key = key_from_name(data.name)
        await self._ensure_available(key=key, name=data.name)
        role = Role(
            key=key,
            name=data.name,
            description=data.description,
            permissions=await self._permissions_by_keys(data.permission_keys),
        )
        self.session.add(role)
        await self._flush_role(role)
        return role

    async def update_role(self, key: str, data: RoleWriteSchema) -> Role:
        role = await self._require_role(key)
        role.description = data.description
        role.permissions = await self._permissions_by_keys(data.permission_keys)
        await self._flush_role(role)
        return role

    async def delete_role(self, key: str) -> None:
        if key == ADMIN_ROLE_KEY:
            raise AppError(
                "conflict",
                "The Admin role cannot be deleted",
                status_code=409,
            )
        role = await self._require_role(key)
        await self.session.delete(role)

    async def _require_role(self, key: str) -> Role:
        role = await self.session.scalar(
            select(Role)
            .where(Role.key == key)
            .options(selectinload(Role.permissions))
        )
        if role is None:
            raise AppError("not_found", "Role not found", status_code=404)
        return role

    async def _ensure_available(self, *, key: str, name: str) -> None:
        exists = await self.session.scalar(select(Role.id).where(Role.key == key))
        if exists is not None:
            raise AppError(
                "conflict",
                "A role with this key already exists",
                status_code=409,
            )
        exists = await self.session.scalar(select(Role.id).where(Role.name == name))
        if exists is not None:
            raise AppError(
                "conflict",
                "A role with this name already exists",
                status_code=409,
            )

    async def _permissions_by_keys(self, keys: list[str]) -> list[Permission]:
        unique_keys = list(dict.fromkeys(keys))
        if not unique_keys:
            return []
        permissions = list(
            await self.session.scalars(
                select(Permission).where(Permission.key.in_(unique_keys))
            )
        )
        if len(permissions) != len(unique_keys):
            raise AppError(
                "invalid_permissions",
                "One or more permissions do not exist",
                status_code=400,
            )
        return permissions

    async def _flush_role(self, role: Role) -> None:
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AppError(
                "conflict",
                "A role with this key or name already exists",
                status_code=409,
            ) from exc
        await self.session.refresh(role, attribute_names=["permissions"])


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
