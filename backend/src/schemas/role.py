from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.rbac.constants import ADMIN_ROLE_KEY
from models.rbac.role import Role
from schemas.key import key_from_name


class RoleRefSchema(BaseModel):
    key: str
    name: str


class PermissionRefSchema(BaseModel):
    key: str
    name: str


class RoleListItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    description: str
    protected: bool
    permissions: list[PermissionRefSchema]

    @classmethod
    def from_role(cls, role: Role) -> Self:
        return cls(
            key=role.key,
            name=role.name,
            description=role.description,
            protected=role.key == ADMIN_ROLE_KEY,
            permissions=sorted(
                (
                    PermissionRefSchema(key=permission.key, name=permission.name)
                    for permission in role.permissions
                ),
                key=lambda item: item.key,
            ),
        )


class RoleListResponseSchema(BaseModel):
    items: list[RoleListItemSchema]
    page: int
    per_page: int
    total: int
    pages: int

    @classmethod
    def from_page(
        cls,
        roles: list[Role],
        *,
        page: int,
        per_page: int,
        total: int,
    ) -> Self:
        pages = (total + per_page - 1) // per_page if per_page and total else 0
        return cls(
            items=[RoleListItemSchema.from_role(role) for role in roles],
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
        )


class RoleWriteSchema(BaseModel):
    description: str = ""
    permission_keys: list[str] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()


class RoleCreateSchema(RoleWriteSchema):
    name: str = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Must be at least 2 characters")
        key_from_name(cleaned)
        return cleaned
