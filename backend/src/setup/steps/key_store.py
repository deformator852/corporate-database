import shutil
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt

from encryption import key_fingerprint
from exceptions import AppError
from key_store import KEY, PREVIOUS, STORES, VaultClient, VaultConfig, key_store

from ..env import ENV_PATH, env_value, remove_env, upsert_env
from ..key import admin_token, read_keys, where
from ..prompts import ask_hidden

# Copied here so the production containers can mount it (docker-compose.prod.yml).
CA_COPY = ENV_PATH.parents[1] / "deploy" / "vault" / "ca.pem"
_VAULT_SETTINGS = ("VAULT_ADDR", "VAULT_ROLE_ID", "VAULT_SECRET_ID", "VAULT_KV_MOUNT", "VAULT_KV_PATH", "VAULT_CACERT")
_CHOICES = {
    "env": ".env file on this server. Simple; a copy of the disk includes the key.",
    "vault": "HashiCorp Vault. The key never touches this disk; needs Vault and an AppRole that may read it.",
}


def _setting(name: str) -> str | None:
    return env_value(ENV_PATH, name)


class KeyStoreStep:
    title = "Encryption key storage"

    def __init__(self, *, installing: bool = False) -> None:
        # Run by setup: Corpus is not running yet, so there is nothing to restart.
        self.installing = installing

    def current(self) -> str | None:
        if _setting("KEY_STORE") is None:
            return None
        return where() if _setting("KEY_STORE") == "vault" else f"the .env file ({where()})"

    def run(self, console: Console) -> None:
        try:
            current = key_store(_setting)
            console.print(f"DATA_ENCRYPTION_KEY is kept in: {where()}")
        except AppError:
            current = "env"
        for index, store in enumerate(STORES, start=1):
            console.print(f"  {index}. {_CHOICES[store]}")
        choice = IntPrompt.ask(
            "Where to keep it", choices=["1", "2"], default=STORES.index(current) + 1, console=console
        )
        target = STORES[choice - 1]
        try:
            if target == "vault":
                _to_vault(console, self.installing)
            elif current == "vault":
                _to_env(console, self.installing)
            else:
                console.print("Keeping the key in .env.")
        except AppError as exc:
            console.print(f"[red]Nothing changed: {exc.message}[/]")


def _keys_to_move() -> str:
    keys = read_keys()
    if keys.get(PREVIOUS):
        raise AppError("conflict", f"A key rotation is in progress ({PREVIOUS} is set); finish it first.", 409)
    key = keys.get(KEY, "")
    if not key:
        raise AppError("misconfigured", f"{KEY} is not set; run uv run setup.", 500)
    return key


def _ask_vault(console: Console) -> VaultConfig:
    def ask(name: str, label: str, default: str = "", *, password: bool = False) -> str:
        current = _setting(name) or default
        if password:
            # Never shown, not even as the default: Enter keeps the current one.
            label += " (hidden while you type or paste" + ("; Enter keeps the current one)" if current else ")")
            return ask_hidden(console, label, current)
        return Prompt.ask(label, default=current or None, console=console) or ""

    ca = ask("VAULT_CACERT", "CA file of Vault's certificate (empty: system CAs)").strip()
    if ca and Path(ca).resolve() != CA_COPY.resolve():
        CA_COPY.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ca, CA_COPY)
    return VaultConfig(
        addr=ask("VAULT_ADDR", "Vault address", "https://vault.example.com:8200").rstrip("/"),
        role_id=ask("VAULT_ROLE_ID", "AppRole role_id"),
        secret_id=ask("VAULT_SECRET_ID", "AppRole secret_id", password=True),
        mount=ask("VAULT_KV_MOUNT", "KV v2 mount", "secret").strip("/"),
        path=ask("VAULT_KV_PATH", "Secret path", "corpus").strip("/"),
        cacert=str(CA_COPY) if ca else "",
    )


def _restart_note(installing: bool) -> str:
    return "" if installing else "\nRestart the backend and the worker (production: deploy/deploy.sh up)."


def _to_vault(console: Console, installing: bool) -> None:
    """Puts the key into Vault (or keeps it there under new settings) and
    removes it from .env once the AppRole has read it back."""
    key = _keys_to_move()
    config = _ask_vault(console)
    client = VaultClient(config)
    stored = client.read(client.login()).get(KEY)
    if stored and stored != key:
        raise AppError(
            "conflict",
            f"Vault already holds another key at {config.mount}/{config.path} "
            f"(fingerprint {key_fingerprint(stored)}); choose another path.",
            409,
        )
    if stored != key:
        client.write(admin_token(console), {KEY: key})
        if client.read(client.login()).get(KEY) != key:
            raise AppError("misconfigured", "The AppRole cannot read the key back; check its policy.", 500)
    upsert_env(ENV_PATH, "KEY_STORE", "vault")
    for name, value in zip(
        _VAULT_SETTINGS,
        (config.addr, config.role_id, config.secret_id, config.mount, config.path, config.cacert),
        strict=True,
    ):
        if value:
            upsert_env(ENV_PATH, name, value)
        else:
            remove_env(ENV_PATH, name)
    remove_env(ENV_PATH, KEY)
    console.print(
        Panel(
            f"The key ({key_fingerprint(key)}) is read from Vault {config.addr}, "
            f"{config.mount}/{config.path}, and is no longer in {ENV_PATH}.\n\n"
            "In Vault, give the AppRole a read-only policy on this path, and bind "
            "its secret_id to this server's address (secret_id_bound_cidrs)." + _restart_note(installing),
            title="Key in Vault",
            style="green",
        )
    )


def _to_env(console: Console, installing: bool) -> None:
    key = _keys_to_move()
    config = VaultConfig.from_values(_setting)
    upsert_env(ENV_PATH, KEY, key)
    upsert_env(ENV_PATH, "KEY_STORE", "env")
    for name in _VAULT_SETTINGS:
        remove_env(ENV_PATH, name)
    console.print(
        Panel(
            f"The key ({key_fingerprint(key)}) is now read from {ENV_PATH}. It is still in "
            f"Vault at {config.mount}/{config.path}: delete it there once it is no longer needed."
            + _restart_note(installing),
            title="Key in .env",
            style="yellow",
        )
    )
