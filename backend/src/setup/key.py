"""DATA_ENCRYPTION_KEY: backup and rotation.

    uv run setup key           fingerprint of the key in .env
    uv run setup key --show    the key itself, to copy it to a safe place
    uv run setup key rotate    start a rotation (see maintenance/rotate_key.py)
"""

import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from encryption import MIN_KEY_LENGTH, key_fingerprint

from .env import ENV_PATH, env_value, random_secret, upsert_env

KEY = "DATA_ENCRYPTION_KEY"
PREVIOUS = "DATA_ENCRYPTION_KEY_PREVIOUS"


def new_key() -> str:
    return random_secret()


def confirm_backup(console: Console, key: str) -> None:
    """Shows the key once and waits until the operator says it is saved:
    without a copy, a lost server disk means lost documents."""
    console.print(
        Panel(
            f"{key}\n\nFingerprint: {key_fingerprint(key)}\n\n"
            "Documents and chats are encrypted with this key. Store a copy "
            "outside this server (password manager, safe), separately from "
            "backups of the data. Without it they cannot be read.",
            title=KEY,
            style="bold yellow",
        )
    )
    if not sys.stdin.isatty():
        console.print(
            "[yellow]Not a terminal: back the key up now with `uv run setup key --show`.[/]"
        )
        return
    while Prompt.ask('Type "saved" once the key is stored', console=console) != "saved":
        pass


def _show(console: Console, reveal: bool) -> None:
    key = env_value(ENV_PATH, KEY) or ""
    if len(key) < MIN_KEY_LENGTH:
        raise SystemExit(f"{KEY} is not set in {ENV_PATH}; run uv run setup.")
    console.print(f"Fingerprint: {key_fingerprint(key)}")
    previous = env_value(ENV_PATH, PREVIOUS)
    if previous:
        console.print(
            f"Rotation in progress; previous key fingerprint: {key_fingerprint(previous)}"
        )
    if reveal:
        console.print(key, soft_wrap=True, highlight=False)
    else:
        console.print("Add --show to print the key itself.")


def _rotate(console: Console) -> None:
    key = env_value(ENV_PATH, KEY) or ""
    if len(key) < MIN_KEY_LENGTH:
        raise SystemExit(f"{KEY} is not set in {ENV_PATH}; run uv run setup.")
    if env_value(ENV_PATH, PREVIOUS):
        raise SystemExit(
            f"A rotation is already in progress ({PREVIOUS} is set). Finish it "
            "with deploy/deploy.sh rotate-key, or python -m maintenance.rotate_key."
        )
    replacement = new_key()
    # Previous first: if writing stops halfway, the old key is still in .env.
    upsert_env(ENV_PATH, PREVIOUS, key)
    upsert_env(ENV_PATH, KEY, replacement)
    console.print(f"Old key kept as {PREVIOUS} ({key_fingerprint(key)}).")
    confirm_backup(console, replacement)
    console.print(
        Panel(
            "Re-encrypt the stored data with the new key:\n"
            "  production:  deploy/deploy.sh rotate-key\n"
            "  development: stop the backend and worker, then\n"
            "               cd backend/src && uv run python -m maintenance.rotate_key\n"
            f"               and remove {PREVIOUS} from .env.\n\n"
            "Until then the app reads both keys and writes with the new one.",
            title="Next",
            style="yellow",
        )
    )


def main(args: list[str]) -> None:
    console = Console()
    if args[:1] == ["rotate"]:
        _rotate(console)
    elif args in ([], ["--show"]):
        _show(console, reveal=args == ["--show"])
    else:
        raise SystemExit(__doc__)
