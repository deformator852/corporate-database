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
from services.document_access import user_permission_keys
from services.grant import ensure_can_grant, ensure_can_manage, role_keys


class RoleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_roles(
        self, page: int = 1, per_page: int = 20, q: str = ""
    ) -> tuple[list[Role], int]:
        filters = _role_search_filters(q)
        count_query = select(func.count()).select_from(Role)
        list_query = select(Role).options(selectinload(Role.permissions))
        if filters:
            count_query = count_query.where(*filters)
            list_query = list_query.where(*filters)
        total = await self.session.scalar(count_query)
        roles = await self.session.scalars(
            list_query.order_by(Role.name, Role.key)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(roles), total or 0

    async def create_role(self, data: RoleCreateSchema, *, actor_id: int) -> Role:
        ensure_can_grant(
            await user_permission_keys(self.session, actor_id), data.permission_keys
        )
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

    async def update_role(
        self, key: str, data: RoleWriteSchema, *, actor_id: int
    ) -> Role:
        actor_keys = await user_permission_keys(self.session, actor_id)
        role = await self._require_role(key)
        ensure_can_manage(actor_keys, role_keys([role]))
        ensure_can_grant(actor_keys, data.permission_keys)
        permissions = await self._permissions_by_keys(data.permission_keys)
        if key == ADMIN_ROLE_KEY and {p.key for p in permissions} != role_keys([role]):
            raise AppError(
                "conflict",
                "The Admin role always has every permission",
                status_code=409,
            )
        role.description = data.description
        role.permissions = permissions
        await self._flush_role(role)
        return role

    async def delete_role(self, key: str, *, actor_id: int) -> Role:
        if key == ADMIN_ROLE_KEY:
            raise AppError(
                "conflict",
                "The Admin role cannot be deleted",
                status_code=409,
            )
        role = await self._require_role(key)
        ensure_can_manage(
            await user_permission_keys(self.session, actor_id), role_keys([role])
        )
        await self.session.delete(role)
        return role

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


def _role_search_filters(q: str) -> list:
    term = q.strip()
    if not term:
        return []
    escaped = (
        term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    pattern = f"%{escaped}%"
    return [
        or_(
            Role.name.ilike(pattern, escape="\\"),
            Role.key.ilike(pattern, escape="\\"),
        )
    ]
