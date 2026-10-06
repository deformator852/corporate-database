from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from schemas.model_config import MODEL_CONFIG


class ErrorSchema(BaseModel):
    model_config = MODEL_CONFIG

    code: str
    message: str


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI entries documenting the common error body for `statuses`."""
    return {status: {"model": ErrorSchema} for status in statuses}


def validation_message(errors: Sequence[Mapping[str, Any]], *, with_field: bool = True) -> str:
    """One readable line for the first validation error, e.g.
    "password: String should have at least 8 characters"."""
    if not errors:
        return "Enter a message."
    first = errors[0]
    message = str(first.get("msg") or "Invalid value").removeprefix("Value error, ")
    field = next((str(part) for part in reversed(first.get("loc", ())) if isinstance(part, str)), "")
    if with_field and field and field not in {"body", "query", "path"}:
        return f"{field}: {message}"
    return message
