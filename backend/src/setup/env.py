import secrets
from pathlib import Path

from rich.console import Console

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
EXAMPLE_PATH = ENV_PATH.with_name(".env.example")


def random_secret(nbytes: int = 32) -> str:
    """URL-safe random token that never starts with "-", which command-line
    tools (mc, psql) would read as an option."""
    while True:
        token = secrets.token_urlsafe(nbytes)
        if not token.startswith("-"):
            return token


def remove_env(path: Path, key: str) -> None:
    """Drops `key` from the file; other lines and comments stay."""
    if not path.exists():
        return
    prefix = f"{key}="
    lines = [line for line in path.read_text().splitlines() if not line.strip().startswith(prefix)]
    path.write_text("\n".join(lines) + "\n")


def _quoted(key: str, value: str) -> str:
    """`value` as .env holds it: single quotes around one with spaces (a
    group name, a button label). Single quotes are literal for python-dotenv,
    Docker Compose and deploy.sh alike, so no character inside is special."""
    if not value or "\n" in value or "\r" in value:
        raise ValueError(f"{key} must be one non-empty line.")
    if not any(ch.isspace() for ch in value) and value[0] not in {'"', "'"}:
        return value
    if "'" in value:
        raise ValueError(f"{key} cannot hold both spaces and a single quote.")
    return f"'{value}'"


def upsert_env(path: Path, key: str, value: str) -> None:
    value = _quoted(key, value)
    prefix = f"{key}="
    lines = path.read_text().splitlines() if path.exists() else []
    out: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix) and not stripped.startswith("#"):
            if not replaced:
                out.append(f"{prefix}{value}")
                replaced = True
            continue
        out.append(line)
    if not replaced:
        if out and out[-1] != "":
            out.append("")
        out.append(f"{prefix}{value}")
    path.write_text("\n".join(out) + "\n")


def env_value(path: Path, key: str) -> str | None:
    prefix = f"{key}="
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix) and not stripped.startswith("#"):
            raw = stripped[len(prefix) :].strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
                return raw[1:-1]
            return raw
    return None


_MINIMAL_ENV = """\
QDRANT_HOST=localhost
QDRANT_PORT=6333
APP_LANGUAGE=en
EMBEDDING_MODEL=multilingual-e5-base
LLM_HOST=http://127.0.0.1:11434
LLM_MODEL=llama3.1:8b
"""


def ensure_env(console: Console) -> None:
    if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
        return
    if EXAMPLE_PATH.exists():
        ENV_PATH.write_text(EXAMPLE_PATH.read_text())
        console.print(f"Created {ENV_PATH} from .env.example.")
        return
    ENV_PATH.write_text(_MINIMAL_ENV)
    console.print(f"Created {ENV_PATH}.")
