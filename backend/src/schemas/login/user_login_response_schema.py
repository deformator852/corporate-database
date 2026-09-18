from pydantic import BaseModel


class UserLoginResponseSchema(BaseModel):
    email: str
