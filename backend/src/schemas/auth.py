from pydantic import BaseModel, ConfigDict

from schemas.email import Email


class UserLoginSchema(BaseModel):
    email: Email
    password: str


class UserLoginResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_name: str
    last_name: str
    email: Email
