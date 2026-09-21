from datetime import datetime
from typing import Self

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.document import Document


class DocumentListItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    filename: str
    status: str
    progress: int
    error_message: str | None
    created_at: datetime

    @classmethod
    def from_document(cls, document: Document) -> Self:
        return cls.model_validate(document)


class DocumentListResponseSchema(BaseModel):
    items: list[DocumentListItemSchema]
    page: int
    per_page: int
    total: int
    pages: int

    @classmethod
    def from_page(
        cls,
        documents: list[Document],
        *,
        page: int,
        per_page: int,
        total: int,
    ) -> Self:
        pages = (total + per_page - 1) // per_page if per_page and total else 0
        return cls(
            items=[DocumentListItemSchema.from_document(document) for document in documents],
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
        )


class DocumentUploadSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(min_length=1, max_length=200)
    file: UploadFile

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter a name.")
        return cleaned


class DocumentUploadResponseSchema(DocumentListItemSchema):
    converted: bool
