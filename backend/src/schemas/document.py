from datetime import datetime
from typing import Self

from fastapi import UploadFile
from pydantic import BaseModel, Field, field_validator

from models.document import Document, DocumentClassification
from schemas.model_config import MODEL_CONFIG, ORM_MODEL_CONFIG, UPLOAD_MODEL_CONFIG
from schemas.page import PageSchema


class DocumentListItemSchema(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    filename: str
    status: str
    progress: int
    error_message: str | None
    classification: DocumentClassification
    created_at: datetime
    # No file in the storage: it cannot be opened or processed again.
    file_missing: bool

    @classmethod
    def from_document(cls, document: Document) -> Self:
        return cls.model_validate(document)


class DocumentListResponseSchema(PageSchema):
    items: list[DocumentListItemSchema]

    @classmethod
    def from_page(
        cls,
        documents: list[Document],
        *,
        page: int,
        per_page: int,
        total: int,
    ) -> Self:
        return cls(
            items=[DocumentListItemSchema.from_document(document) for document in documents],
            page=page,
            per_page=per_page,
            total=total,
        )


class DocumentUploadSchema(BaseModel):
    model_config = UPLOAD_MODEL_CONFIG

    name: str = Field(min_length=1, max_length=200)
    classification: DocumentClassification = DocumentClassification.STANDARD
    file: UploadFile

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter a name.")
        return cleaned


class DocumentUpdateSchema(BaseModel):
    """Fields left out stay as they are."""

    model_config = MODEL_CONFIG

    name: str | None = Field(default=None, min_length=1, max_length=200)
    classification: DocumentClassification | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter a name.")
        return cleaned


class DocumentChunkSchema(BaseModel):
    """A passage of a document, as search stores it."""

    model_config = MODEL_CONFIG

    text: str
    # 1-based PDF page it starts on; null for other files.
    page: int | None


class DocumentUploadResponseSchema(DocumentListItemSchema):
    converted: bool
