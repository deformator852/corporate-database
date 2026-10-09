from typing import Annotated

import email_validator
from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator

# Company networks name their mail domains company.local (the Active Directory
# habit); the library refuses .local as reserved for multicast DNS. The other
# special-use names (invalid, localhost, onion, ...) stay refused.
email_validator.SPECIAL_USE_DOMAIN_NAMES = [
    name for name in email_validator.SPECIAL_USE_DOMAIN_NAMES if name != "local"
]


def normalize_email(value: str) -> str:
    """The address as stored: validated and lower-cased; ValueError if invalid."""
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


Email = Annotated[str, AfterValidator(normalize_email)]
