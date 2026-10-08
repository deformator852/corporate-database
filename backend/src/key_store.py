"""Where DATA_ENCRYPTION_KEY (and, mid-rotation, DATA_ENCRYPTION_KEY_PREVIOUS)
comes from, chosen by KEY_STORE in `uv run setup` / `uv run configure`.

KEY_STORE=env (default): the environment, that is backend/.env.

KEY_STORE=vault: HashiCorp Vault. The keys are fields of a KV v2 secret
(VAULT_KV_MOUNT, default "secret"; VAULT_KV_PATH, default "corpus"), read once
per process after an AppRole login (VAULT_ROLE_ID, VAULT_SECRET_ID); they are
held in memory only. .env keeps the AppRole credentials, not the key: a copy
of the disk is no use away from the company network, and the operator can
bind the secret id to the server's address in Vault, revoke it, and see every
read in Vault's audit log.

VAULT_ADDR is Vault's address. VAULT_CACERT is a CA file for a Vault
certificate signed by a company CA. VAULT_CONNECT (host:port) is where to
connect instead of VAULT_ADDR's host, with TLS still checked against that
host: production containers have no route out and reach Vault through the
`vault-tunnel` service (docker-compose.prod.yml).
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Any
from urllib.parse import urlsplit

import httpx

from exceptions import AppError

KEY = "DATA_ENCRYPTION_KEY"
PREVIOUS = "DATA_ENCRYPTION_KEY_PREVIOUS"
STORES = ("env", "vault")
_TIMEOUT = httpx.Timeout(10.0)


@dataclass(frozen=True, slots=True)
class VaultConfig:
    addr: str
    role_id: str
    secret_id: str
    mount: str = "secret"
    path: str = "corpus"
    cacert: str = ""
    connect: str = ""

    @classmethod
    def from_values(cls, value: Callable[[str], str | None]) -> VaultConfig:
        """From VAULT_* settings read by `value` (the environment, or .env in setup)."""

        def get(name: str, default: str = "") -> str:
            return (value(name) or "").strip() or default

        config = cls(
            addr=get("VAULT_ADDR").rstrip("/"),
            role_id=get("VAULT_ROLE_ID"),
            secret_id=get("VAULT_SECRET_ID"),
            mount=get("VAULT_KV_MOUNT", "secret").strip("/"),
            path=get("VAULT_KV_PATH", "corpus").strip("/"),
            cacert=get("VAULT_CACERT"),
            connect=get("VAULT_CONNECT"),
        )
        missing = [
            name
            for name, field in (
                ("VAULT_ADDR", config.addr),
                ("VAULT_ROLE_ID", config.role_id),
                ("VAULT_SECRET_ID", config.secret_id),
            )
            if not field
        ]
        if missing:
            raise AppError("misconfigured", f"KEY_STORE is vault, but {', '.join(missing)} is not set.", 500)
        return config


class VaultClient:
    def __init__(self, config: VaultConfig, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config
        self.transport = transport

    def login(self) -> str:
        """An AppRole token, valid as long as the role allows."""
        body = self._request(
            "POST",
            "auth/approle/login",
            json={
                "role_id": self.config.role_id,
                "secret_id": self.config.secret_id,
            },
        )
        token = (body.get("auth") or {}).get("client_token")
        if not isinstance(token, str):
            raise AppError("misconfigured", "Vault returned no token for the AppRole login.", 500)
        return token

    def read(self, token: str) -> dict[str, str]:
        """The fields of the secret; empty when there is none yet."""
        body = self._request("GET", self._secret_path(), token=token, missing_ok=True)
        data = ((body.get("data") or {}).get("data")) or {}
        return {str(name): str(value) for name, value in data.items()}

    def write(self, token: str, fields: dict[str, str]) -> None:
        """Replaces the secret with `fields` (a new KV version)."""
        self._request("POST", self._secret_path(), token=token, json={"data": fields})

    def _secret_path(self) -> str:
        return f"{self.config.mount}/data/{self.config.path}"

    def _request(
        self, method: str, path: str, *, token: str | None = None, json: Any = None, missing_ok: bool = False
    ) -> dict[str, Any]:
        target = urlsplit(self.config.addr)
        url = f"{self.config.addr}/v1/{path}"
        headers = {"X-Vault-Token": token} if token else {}
        extensions: dict[str, Any] = {}
        if self.config.connect:
            # Dial the tunnel, but speak to Vault: Host header and TLS name.
            url = f"{target.scheme}://{self.config.connect}/v1/{path}"
            headers["Host"] = target.netloc
            extensions["sni_hostname"] = target.hostname
        verify: Any = self.config.cacert or True
        try:
            with httpx.Client(timeout=_TIMEOUT, verify=verify, transport=self.transport) as client:
                response = client.request(method, url, headers=headers, json=json, extensions=extensions)
        except httpx.HTTPError as exc:
            raise AppError("unavailable", f"Could not reach Vault at {self.config.addr}: {exc}", 503) from exc
        if response.status_code == 404 and missing_ok:
            return {}
        if response.status_code >= 400:
            try:
                errors = "; ".join(response.json().get("errors") or []) or response.reason_phrase
            except ValueError:
                errors = response.reason_phrase
            raise AppError("misconfigured", f"Vault refused {method} {path} ({response.status_code}): {errors}", 500)
        return response.json() if response.content else {}


def key_store(value: Callable[[str], str | None] = os.getenv) -> str:
    store = (value("KEY_STORE") or "env").strip().lower()
    if store not in STORES:
        raise AppError("misconfigured", f"KEY_STORE must be one of {', '.join(STORES)}.", 500)
    return store


@cache
def _vault_keys() -> dict[str, str]:
    client = VaultClient(VaultConfig.from_values(os.getenv))
    return client.read(client.login())


def secret(name: str) -> str:
    """DATA_ENCRYPTION_KEY or DATA_ENCRYPTION_KEY_PREVIOUS from the configured store."""
    if key_store() == "vault":
        return _vault_keys().get(name, "").strip()
    return (os.getenv(name) or "").strip()


def forget() -> None:
    """Reads the store again on next use (tests, rotation)."""
    _vault_keys.cache_clear()
