from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from exceptions import AppError
from models.rbac.association import role_users
from models.rbac.constants import ADMIN_ROLE_KEY
from models.rbac.role import Role
from models.user import User
from schemas.user import UserCreateSchema, UserUpdateSchema
from services.password import hash_password


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_users(
        self, page: int = 1, per_page: int = 20
    ) -> tuple[list[User], int]:
        total = await self.session.scalar(select(func.count()).select_from(User))
        users = await self.session.scalars(
            select(User)
            .options(selectinload(User.roles))
            .order_by(User.last_name, User.first_name, User.id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(users), total or 0

    async def get_user(self, user_id: int) -> User | None:
        return await self.session.scalar(
            select(User).where(User.id == user_id).options(selectinload(User.roles))
        )

    async def create_user(self, data: UserCreateSchema) -> User:
        await self._ensure_email_available(data.email)
        user = User(
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            password=hash_password(data.password),
            roles=await self._roles_by_keys(data.role_keys),
        )
        self.session.add(user)
        await self._flush_user(user)
        return user

    async def update_user(self, user_id: int, data: UserUpdateSchema) -> User:
        user = await self._require_user(user_id)
        await self._ensure_email_available(data.email, exclude_id=user.id)
        next_roles = await self._roles_by_keys(data.role_keys)
        await self._guard_last_admin(user, next_roles)
        user.first_name = data.first_name
        user.last_name = data.last_name
        user.email = data.email
        user.roles = next_roles
        if data.password is not None:
            user.password = hash_password(data.password)
        await self._flush_user(user)
        return user

    async def delete_user(self, user_id: int, *, actor_id: int) -> None:
        user = await self._require_user(user_id)
        if user.id == actor_id:
            raise AppError(
                "conflict",
                "You cannot delete your own account",
                status_code=409,
            )
        await self._guard_last_admin(user, [])
        await self.session.delete(user)

    async def _require_user(self, user_id: int) -> User:
        user = await self.get_user(user_id)
        if user is None:
            raise AppError("not_found", "User not found", status_code=404)
        return user

    async def _ensure_email_available(
        self, email: str, *, exclude_id: int | None = None
    ) -> None:
        query = select(User.id).where(User.email == email)
        if exclude_id is not None:
            query = query.where(User.id != exclude_id)
        exists = await self.session.scalar(query)
        if exists is not None:
            raise AppError(
                "conflict",
                "A user with this email already exists",
                status_code=409,
            )

    async def _roles_by_keys(self, keys: list[str]) -> list[Role]:
        unique_keys = list(dict.fromkeys(keys))
        if not unique_keys:
            return []
        roles = list(
            await self.session.scalars(select(Role).where(Role.key.in_(unique_keys)))
        )
        if len(roles) != len(unique_keys):
            raise AppError(
                "invalid_roles",
                "One or more roles do not exist",
                status_code=400,
            )
        return roles

    async def admin_ids(self) -> set[int]:
        ids = await self.session.scalars(
            select(role_users.c.user_id)
            .join(Role, Role.id == role_users.c.role_id)
            .where(Role.key == ADMIN_ROLE_KEY)
        )
        return set(ids)

    def _is_admin(self, roles: list[Role]) -> bool:
        return any(role.key == ADMIN_ROLE_KEY for role in roles)

    async def _guard_last_admin(self, user: User, next_roles: list[Role]) -> None:
        if not self._is_admin(user.roles) or self._is_admin(next_roles):
            return
        admin_ids = await self.admin_ids()
        if admin_ids <= {user.id}:
            raise AppError(
                "conflict",
                "The Admin role cannot be removed from the last admin",
                status_code=409,
            )

    async def _flush_user(self, user: User) -> None:
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AppError(
                "conflict",
                "A user with this email already exists",
                status_code=409,
            ) from exc
        await self.session.refresh(user, attribute_names=["roles"])
