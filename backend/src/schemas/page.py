from pydantic import BaseModel, computed_field

from schemas.model_config import MODEL_CONFIG


class PageSchema(BaseModel):
    """A numbered page of a list. Subclasses add `items` (and any totals of
    their own)."""

    model_config = MODEL_CONFIG

    page: int
    per_page: int
    total: int

    @computed_field
    @property
    def pages(self) -> int:
        return -(-self.total // self.per_page) if self.per_page > 0 else 0
