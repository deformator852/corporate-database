from datetime import datetime
from typing import Literal, Self

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
    # Continue a saved chat; None starts a new one.
    conversation_id: int | None = Field(default=None, ge=1)


class ChatCancelSchema(BaseModel):
    model_config = MODEL_CONFIG

    type: Literal["cancel"]


class ChatSourceSchema(BaseModel):
    """A document an answer was built from."""

    model_config = MODEL_CONFIG

    id: int
    name: str
    filename: str


class ChatAnswerSchema(BaseModel):
    model_config = MODEL_CONFIG

    type: Literal["answer"]
    content: str
    conversation_id: int
    sources: list[ChatSourceSchema] = Field(default_factory=list)


class ChatDeltaSchema(BaseModel):
    """A piece of the answer while it is generated; `answer` follows with the
    full text."""

    model_config = MODEL_CONFIG

    type: Literal["delta"]
    content: str


class ChatCancelledSchema(BaseModel):
    model_config = MODEL_CONFIG

    type: Literal["cancelled"]


class ChatSocketErrorSchema(BaseModel):
    model_config = MODEL_CONFIG

    type: Literal["error"]
    code: str
    message: str


class ChatHistoryMessageSchema(BaseModel):
    model_config = MODEL_CONFIG

    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[ChatSourceSchema]
    created_at: datetime


class ChatConversationItemSchema(BaseModel):
    model_config = MODEL_CONFIG

    id: int
    title: str
    updated_at: datetime


class ChatConversationListSchema(BaseModel):
    model_config = MODEL_CONFIG

    items: list[ChatConversationItemSchema]
    page: int
    per_page: int
    total: int
    pages: int

    @classmethod
    def from_page(cls, items: list, *, page: int, per_page: int, total: int) -> Self:
        pages = (total + per_page - 1) // per_page if per_page and total else 0
        return cls(
            items=[
                ChatConversationItemSchema(id=c.id, title=c.title, updated_at=c.updated_at)
                for c in items
            ],
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
        )


class ChatConversationSchema(BaseModel):
    model_config = MODEL_CONFIG

    id: int
    title: str
    messages: list[ChatHistoryMessageSchema]

    @classmethod
    def from_conversation(cls, conversation) -> Self:
        return cls(
            id=conversation.id,
            title=conversation.title,
            messages=[
                ChatHistoryMessageSchema(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    sources=[ChatSourceSchema(**source) for source in m.sources],
                    created_at=m.created_at,
                )
                for m in conversation.messages
            ],
        )
