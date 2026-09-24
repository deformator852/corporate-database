from typing import Self

from pydantic import BaseModel

from models.user import User
from schemas.email import Email
from schemas.model_config import MODEL_CONFIG, ORM_MODEL_CONFIG


class LoginSchema(BaseModel):
    model_config = MODEL_CONFIG

    email: Email
    password: str


class SessionUserSchema(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    first_name: str
    last_name: str
    email: Email
    permissions: list[str]

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            permissions=sorted(
                {
                    permission.key
                    for role in user.roles
                    for permission in role.permissions
                }
            ),
        )
