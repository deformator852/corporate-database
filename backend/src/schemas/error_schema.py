from pydantic import BaseModel


class ErrorSchema(BaseModel):
    code: str
    message: str
