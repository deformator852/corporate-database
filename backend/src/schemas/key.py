import re

_NON_KEY = re.compile(r"[^a-z0-9]+")
_KEY_MAX_LENGTH = 50


def key_from_name(name: str) -> str:
    cleaned = _NON_KEY.sub(".", name.strip().lower()).strip(".")
    if len(cleaned) < 2:
        raise ValueError("Name must produce a key of at least 2 characters")
    if len(cleaned) > _KEY_MAX_LENGTH:
        raise ValueError("Name produces a key that is too long")
    if not cleaned[0].isalpha():
        raise ValueError("Name must start with a letter")
    return cleaned
