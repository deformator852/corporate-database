from pydantic import BaseModel

from schemas.model_config import MODEL_CONFIG


class ErrorSchema(BaseModel):
    model_config = MODEL_CONFIG

    code: str
    message: str
