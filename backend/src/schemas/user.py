from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.user import User
from schemas.email import Email


class RoleRefSchema(BaseModel):
    key: str
    name: str


class UserListItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: Email
    roles: list[RoleRefSchema]
    is_last_admin: bool

    @classmethod
    def from_user(cls, user: User, *, is_last_admin: bool = False) -> Self:
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            roles=sorted(
                (RoleRefSchema(key=role.key, name=role.name) for role in user.roles),
                key=lambda role: role.name,
            ),
            is_last_admin=is_last_admin,
        )


class UserListResponseSchema(BaseModel):
    items: list[UserListItemSchema]
    page: int
    per_page: int
    total: int
    pages: int

    @classmethod
    def from_page(
        cls,
        users: list[User],
        *,
        page: int,
        per_page: int,
        total: int,
        admin_ids: set[int],
    ) -> Self:
        pages = (total + per_page - 1) // per_page if per_page and total else 0
        last_admin_id = next(iter(admin_ids)) if len(admin_ids) == 1 else None
        return cls(
            items=[
                UserListItemSchema.from_user(
                    user,
                    is_last_admin=user.id == last_admin_id,
                )
                for user in users
            ],
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
        )


class UserWriteSchema(BaseModel):
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    email: Email
    role_keys: list[str] = Field(default_factory=list)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Must be at least 2 characters")
        return cleaned


class UserCreateSchema(UserWriteSchema):
    password: str = Field(min_length=8, max_length=100)


class UserUpdateSchema(UserWriteSchema):
    password: str | None = Field(default=None, min_length=8, max_length=100)

    @field_validator("password", mode="before")
    @classmethod
    def empty_password(cls, value: object) -> object:
        if value == "":
            return None
        return value
