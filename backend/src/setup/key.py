"""DATA_ENCRYPTION_KEY: backup and rotation, from .env or HashiCorp Vault.

uv run configure key           fingerprint of the key
uv run configure key --show    the key itself, to copy it to a safe place
uv run configure key rotate    start a rotation (see maintenance/rotate_key.py)
uv run configure key finish    drop the old key once the data is re-encrypted
"""

import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from encryption import MIN_KEY_LENGTH, key_fingerprint
from exceptions import AppError
from key_store import KEY, PREVIOUS, VaultClient, VaultConfig, key_store

from .env import ENV_PATH, env_value, random_secret, remove_env, upsert_env
from .prompts import ask_hidden


def new_key() -> str:
    return random_secret()


def _setting(name: str) -> str | None:
    return env_value(ENV_PATH, name)


def in_vault() -> bool:
    return key_store(_setting) == "vault"


def vault_client() -> VaultClient:
    return VaultClient(VaultConfig.from_values(_setting))


def read_keys() -> dict[str, str]:
    """KEY and, mid-rotation, PREVIOUS from the configured store."""
    if in_vault():
        client = vault_client()
        return client.read(client.login())
    return {name: value for name in (KEY, PREVIOUS) if (value := _setting(name))}


def admin_token(console: Console) -> str:
    """A Vault token that may write the secret; used once, never saved.
    The app's AppRole only needs to read it."""
    console.print("A Vault token that may write the secret is needed once; it is not saved.")
    return ask_hidden(console, "Vault token (hidden while you type or paste; not saved)")


def write_keys(console: Console, keys: dict[str, str]) -> None:
    """Stores exactly `keys` (KEY, and PREVIOUS during a rotation)."""
    if in_vault():
        vault_client().write(admin_token(console), keys)
        return
    # PREVIOUS first: if writing stops halfway, the old key is not lost.
    for name in (PREVIOUS, KEY):
        if name in keys:
            upsert_env(ENV_PATH, name, keys[name])
        else:
            remove_env(ENV_PATH, name)


def where() -> str:
    if in_vault():
        config = VaultConfig.from_values(_setting)
        return f"Vault {config.addr}, {config.mount}/{config.path}"
    return str(ENV_PATH)


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
        console.print("[yellow]Not a terminal: back the key up now with `uv run configure key --show`.[/]")
        return
    while Prompt.ask('Type "saved" once the key is stored', console=console) != "saved":
        pass


def _current(keys: dict[str, str]) -> str:
    key = keys.get(KEY, "")
    if len(key) < MIN_KEY_LENGTH:
        raise SystemExit(f"{KEY} is not set in {where()}; run uv run install.")
    return key


def _show(console: Console, reveal: bool) -> None:
    keys = read_keys()
    key = _current(keys)
    console.print(f"Key in {where()}. Fingerprint: {key_fingerprint(key)}")
    if keys.get(PREVIOUS):
        console.print(f"Rotation in progress; previous key fingerprint: {key_fingerprint(keys[PREVIOUS])}")
    if reveal:
        console.print(key, soft_wrap=True, highlight=False)
    else:
        console.print("Add --show to print the key itself.")


def _rotate(console: Console) -> None:
    keys = read_keys()
    key = _current(keys)
    if keys.get(PREVIOUS):
        raise SystemExit(
            f"A rotation is already in progress ({PREVIOUS} is set). Finish it "
            "with deploy/deploy.sh rotate-key, or python -m maintenance.rotate_key."
        )
    replacement = new_key()
    write_keys(console, {PREVIOUS: key, KEY: replacement})
    console.print(f"Old key kept as {PREVIOUS} ({key_fingerprint(key)}).")
    confirm_backup(console, replacement)
    finish = "uv run configure key finish" if in_vault() else f"remove {PREVIOUS} from .env"
    console.print(
        Panel(
            "Re-encrypt the stored data with the new key:\n"
            "  production:  deploy/deploy.sh rotate-key\n"
            "  development: stop the backend and worker, then\n"
            "               cd backend/src && uv run python -m maintenance.rotate_key\n"
            f"               and {finish}.\n\n"
            "Until then the app reads both keys and writes with the new one.",
            title="Next",
            style="yellow",
        )
    )


def _finish(console: Console) -> None:
    keys = read_keys()
    key = _current(keys)
    if not keys.get(PREVIOUS):
        console.print("No rotation in progress.")
        return
    write_keys(console, {KEY: key})
    console.print(f"{PREVIOUS} removed from {where()}; only {key_fingerprint(key)} is used now.")


def main(args: list[str]) -> None:
    console = Console()
    try:
        if args[:1] == ["rotate"]:
            _rotate(console)
        elif args[:1] == ["finish"]:
            _finish(console)
        elif args in ([], ["--show"]):
            _show(console, reveal=args == ["--show"])
        else:
            raise SystemExit(__doc__)
    except AppError as exc:  # Vault unreachable or refusing
        raise SystemExit(exc.message) from None
