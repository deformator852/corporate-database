from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.model_config import MODEL_CONFIG


class ChatMessageSchema(BaseModel):
    model_config = MODEL_CONFIG

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter a message.")
        return cleaned


class ChatRequestSchema(BaseModel):
    model_config = MODEL_CONFIG

    messages: list[ChatMessageSchema] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def last_message_from_user(self) -> "ChatRequestSchema":
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user.")
        return self


class ChatAskSchema(ChatRequestSchema):
    type: Literal["ask"]


class ChatCancelSchema(BaseModel):
    model_config = MODEL_CONFIG

    type: Literal["cancel"]


class ChatAnswerSchema(BaseModel):
    model_config = MODEL_CONFIG

    type: Literal["answer"]
    content: str


class ChatCancelledSchema(BaseModel):
    model_config = MODEL_CONFIG

    type: Literal["cancelled"]


class ChatSocketErrorSchema(BaseModel):
    model_config = MODEL_CONFIG

    type: Literal["error"]
    code: str
    message: str
