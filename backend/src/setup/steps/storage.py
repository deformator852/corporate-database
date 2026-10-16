"""Where document files are kept: on this server (default) or in the
company's own S3-compatible storage (services/storage.py)."""

import shutil
import uuid
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from exceptions import AppError
from settings import S3Config

from ..env import ENV_PATH, env_value, remove_env, upsert_env

CA_COPY = ENV_PATH.parents[1] / "deploy" / "s3" / "ca.pem"
_S3_SETTINGS = ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION", "S3_CACERT")


def _setting(name: str) -> str | None:
    return env_value(ENV_PATH, name)


def _ask_s3(console: Console) -> S3Config:
    def ask(name: str, label: str, default: str = "") -> str:
        return (Prompt.ask(label, default=_setting(name) or default or None, console=console) or "").strip()

    while True:
        endpoint = ask("S3_ENDPOINT", "Storage address (https://host[:port])").rstrip("/")
        if endpoint.startswith(("https://", "http://")) and endpoint.count("/") == 2:
            break
        console.print("Enter the address as https://host or https://host:port, without a path.")
    if endpoint.startswith("http://"):
        console.print("[yellow]Plain http: the files are encrypted anyway, but use https if the storage offers it.[/]")
    bucket = ask("S3_BUCKET", "Bucket")
    access_key = ask("S3_ACCESS_KEY", "Access key")
    current = _setting("S3_SECRET_KEY")
    # Hidden, and never shown as the default: it is a password.
    secret_key = Prompt.ask(
        "Secret key (hidden while you type or paste" + ("; Enter keeps the current one)" if current else ")"),
        password=True,
        default=current or "",
        show_default=False,
        console=console,
    ).strip()
    region = ask("S3_REGION", "Region", "us-east-1")
    ca = ask("S3_CACERT", "CA file of the storage's certificate (empty: public CAs)")
    if ca and Path(ca).resolve() != CA_COPY.resolve():
        CA_COPY.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ca, CA_COPY)
    return S3Config(
        endpoint=endpoint,
        bucket=bucket,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        cacert=str(CA_COPY) if ca else "",
    )


def check_access(config: S3Config) -> None:
    """Writes, reads back and deletes a test object: what Corpus does with
    every document. Raises AppError with the storage's reason."""
    from services.storage import S3Store

    try:
        store = S3Store(config)
    except ValueError as exc:  # the client refuses the address itself (a bad port)
        raise AppError("invalid", f"The storage address is not valid: {exc}", status_code=400) from exc
    key = f"corpus-check/{uuid.uuid4()}"
    probe = b"Corpus storage check"
    try:
        store.write(key, probe)
        if store.read(key) != probe:
            raise AppError("misconfigured", "The storage returned other data than was written.", status_code=500)
        store.remove(key)
    except AppError as exc:
        # The storage's own words (AccessDenied, NoSuchBucket, a refused
        # certificate); they never hold the secret key.
        raise AppError(exc.code, f"{exc.message} {exc.__cause__ or ''}".strip(), status_code=exc.status_code) from exc


class StorageStep:
    title = "Document storage"

    def current(self) -> str | None:
        kind = _setting("STORAGE")
        if kind is None:
            return None
        if kind == "s3":
            return f"the company's S3 storage: bucket {_setting('S3_BUCKET')} at {_setting('S3_ENDPOINT')}"
        return "files on this server"

    def run(self, console: Console) -> None:
        console.print(
            "Uploaded files are kept encrypted, either on this server (a Docker volume in production) or in "
            "the company's own S3-compatible storage (Ceph, NetApp StorageGRID, Dell ECS, AWS S3 and others), "
            "which keeps its own copies and backups."
        )
        console.print(
            "[yellow]Choose before the first upload: switching later moves no files "
            "(documentations/deployment.md shows how to copy them).[/]"
        )
        use_s3 = Confirm.ask(
            "Keep the files in the company's S3 storage?", default=_setting("STORAGE") == "s3", console=console
        )
        if not use_s3:
            upsert_env(ENV_PATH, "STORAGE", "disk")
            for name in _S3_SETTINGS:
                remove_env(ENV_PATH, name)
            console.print("Document files are kept on this server.")
            return
        config = _ask_s3(console)
        console.print("Checking that Corpus can write, read and delete in the bucket…")
        try:
            check_access(config)
        except AppError as exc:
            console.print(f"[red]{exc.message}[/]")
            if not Confirm.ask("Save these settings anyway?", default=False, console=console):
                console.print("Nothing changed.")
                return
        else:
            console.print("[green]The storage works.[/]")
        upsert_env(ENV_PATH, "STORAGE", "s3")
        for name, value in zip(
            _S3_SETTINGS,
            (config.endpoint, config.bucket, config.access_key, config.secret_key, config.region, config.cacert),
            strict=True,
        ):
            if value:
                upsert_env(ENV_PATH, name, value)
            else:
                remove_env(ENV_PATH, name)
        console.print(
            Panel(
                f"At the storage, give this account only s3:GetObject, s3:PutObject and s3:DeleteObject "
                f"on {config.bucket}/*. Back the bucket up with the storage's own versioning or replication: "
                "deploy/deploy.sh backup does not copy it.\n"
                "Restart the backend and the worker (production: deploy/deploy.sh up).",
                title="Files in S3",
                style="green",
            )
        )
