from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, field_validator

from models.user import User
from schemas.email import Email
from schemas.model_config import MODEL_CONFIG, ORM_MODEL_CONFIG
from schemas.role import RoleRefSchema
from services.password import MAX_PASSWORD_BYTES, password_fits


class UserListItemSchema(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    first_name: str
    last_name: str
    email: Email
    roles: list[RoleRefSchema]
    is_last_admin: bool
    disabled: bool

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
            disabled=user.is_disabled,
        )


class UserListResponseSchema(BaseModel):
    model_config = MODEL_CONFIG

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
    model_config = MODEL_CONFIG

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


def _password_fits(value: str | None) -> str | None:
    if value is not None and not password_fits(value):
        raise ValueError(f"Password is too long (max {MAX_PASSWORD_BYTES} bytes; non-Latin letters take 2 bytes each)")
    return value


class UserCreateSchema(UserWriteSchema):
    password: str = Field(min_length=8, max_length=100)

    _fits = field_validator("password")(_password_fits)


class UserUpdateSchema(UserWriteSchema):
    password: str | None = Field(default=None, min_length=8, max_length=100)

    @field_validator("password", mode="before")
    @classmethod
    def empty_password(cls, value: object) -> object:
        if value == "":
            return None
        return value

    _fits = field_validator("password")(_password_fits)


class UserDetailSchema(BaseModel):
    """User page: profile plus a summary of their audit history."""

    model_config = MODEL_CONFIG

    id: int
    first_name: str
    last_name: str
    email: Email
    roles: list[RoleRefSchema]
    disabled: bool
    created_at: datetime
    last_sign_in_at: datetime | None
    actions_total: int

    @classmethod
    def from_user(cls, user: User, *, actions_total: int, last_sign_in_at: datetime | None) -> Self:
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            roles=sorted(
                (RoleRefSchema(key=role.key, name=role.name) for role in user.roles),
                key=lambda role: role.name,
            ),
            disabled=user.is_disabled,
            created_at=user.created_at,
            last_sign_in_at=last_sign_in_at,
            actions_total=actions_total,
        )
