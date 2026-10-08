from pydantic import BaseModel

from schemas.model_config import MODEL_CONFIG


class ReindexSchema(BaseModel):
    """Search being rebuilt for a new embedding model."""

    model_config = MODEL_CONFIG

    active: bool
    # Share of the documents embedded again, 0-100.
    percent: int
