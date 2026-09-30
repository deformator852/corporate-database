from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator


def _normalize_email(value: str) -> str:
    try:
        result = validate_email(
            value,
            check_deliverability=False,
            test_environment=True,
        )
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    # Case-insensitive in practice: Ana@Acme.io and ana@acme.io are one person.
    return result.normalized.lower()


Email = Annotated[str, AfterValidator(_normalize_email)]
