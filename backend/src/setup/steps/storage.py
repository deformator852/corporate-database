"""Where document files are kept: on this server (default) or in the
company's own S3-compatible storage (services/storage.py)."""

import asyncio
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Literal

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


def _current_s3() -> S3Config | None:
    if _setting("STORAGE") != "s3":
        return None
    return S3Config(
        endpoint=_setting("S3_ENDPOINT") or "",
        bucket=_setting("S3_BUCKET") or "",
        access_key=_setting("S3_ACCESS_KEY") or "",
        secret_key=_setting("S3_SECRET_KEY") or "",
        region=_setting("S3_REGION") or "us-east-1",
        cacert=_setting("S3_CACERT") or "",
    )


def _store(s3: S3Config | None):
    """The store of `s3`, or of this server's folder (development)."""
    from services.storage import DiskStore, S3Store
    from settings import storage_dir

    return S3Store(s3) if s3 else DiskStore(storage_dir())


def _upstream(endpoint: str) -> str:
    """host:port of an endpoint, as deploy/deploy.sh aims s3-tunnel."""
    host = endpoint.split("://", 1)[1]
    return host if ":" in host else host + (":443" if endpoint.startswith("https:") else ":80")


# Moved in production: Corpus was stopped for it, and starts once the new
# storage is saved.
Move = Literal["moved", "moved in production", "not moved", "failed"]


def offer_move(console: Console, source: S3Config | None, target: S3Config | None) -> Move:
    """Offers to copy the document files from the current storage to the
    new one (None: this server), before the new one is saved."""
    if (source and (source.endpoint, source.bucket)) == (target and (target.endpoint, target.bucket)):
        return "not moved"
    from switch_embedding_model import production_running

    if production_running():
        return _move_in_production(console, source, target)
    return _move_here(console, source, target)


def _ask_to_move(console: Console, what: str) -> bool:
    if Confirm.ask(f"Move {what} to the new storage?", default=True, console=console):
        return True
    console.print(
        "[yellow]Files stay where they are: documents uploaded so far show as having no file "
        "until they are copied (documentations/deployment.md).[/]"
    )
    return False


def _move_here(console: Console, source: S3Config | None, target: S3Config | None) -> Move:
    """Development: the backend's folder or S3 storage, from this process."""
    from maintenance.move_files import document_keys, move, summary

    try:
        keys = asyncio.run(document_keys())
    except Exception as exc:  # noqa: BLE001 - no database yet means nothing to move
        console.print(f"[yellow]Could not list the documents ({type(exc).__name__}); no files were moved.[/]")
        return "not moved"
    if not keys or not _ask_to_move(console, f"the files of {len(keys)} document(s)"):
        return "not moved"
    try:
        moved = move(keys, _store(source), _store(target), console.print)
    except AppError as exc:
        console.print(f"[red]Moving stopped: {exc.message} {exc.__cause__ or ''}[/]")
        return "failed"
    console.print(f"[green]{summary(moved)}[/]")
    return "moved"


def _move_in_production(console: Console, source: S3Config | None, target: S3Config | None) -> Move:
    """Production: inside the backend image, which sees the documents_data
    volume and reaches S3 through s3-tunnel. The backend and the worker stop
    meanwhile, or an upload could miss the move."""
    from switch_embedding_model import compose

    if source and target and _upstream(source.endpoint) != _upstream(target.endpoint):
        console.print(
            "[yellow]s3-tunnel reaches one storage at a time: copy the files between the two S3 "
            "storages with their own tools.[/]"
        )
        return "not moved"
    if not _ask_to_move(console, "the document files"):
        return "not moved"
    s3 = target or source
    assert s3 is not None  # one of them is S3: they differ
    # Through the environment, not the command line, where the secret key would show.
    names = {"TARGET_STORAGE": "s3" if target else "disk", "S3_UPSTREAM": _upstream(s3.endpoint)}
    if target:
        names |= {
            "TARGET_S3_ENDPOINT": target.endpoint,
            "TARGET_S3_BUCKET": target.bucket,
            "TARGET_S3_ACCESS_KEY": target.access_key,
            "TARGET_S3_SECRET_KEY": target.secret_key,
            "TARGET_S3_REGION": target.region,
            "TARGET_S3_CACERT": "/etc/corpus-s3/ca.pem" if target.cacert else "",
            "TARGET_S3_CONNECT": "s3-tunnel:9000",
        }
    else:
        names["TARGET_STORAGE_DIR"] = "/data/documents"
    os.environ.update(names)
    passed = [arg for name in names if name.startswith("TARGET_") for arg in ("-e", name)]
    console.print("Stopping the backend and the worker...")
    try:
        compose("stop", "backend", "worker")
        compose("--profile", "s3", "up", "-d", "s3-tunnel")
        compose("run", "--rm", "--no-deps", *passed, "backend", "python", "-m", "maintenance.move_files")
    except subprocess.CalledProcessError:
        console.print("[red]Moving stopped (see above); starting Corpus again with the old storage.[/]")
        restart_production(console)
        return "failed"
    return "moved in production"


def restart_production(console: Console) -> None:
    from switch_embedding_model import REPO_DIR, stack_env

    console.print("Starting Corpus (deploy/deploy.sh up)...")
    subprocess.run([str(REPO_DIR / "deploy" / "deploy.sh"), "up"], check=False, env=stack_env())


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
        console.print("Switching later offers to move the files already uploaded to the new storage.")
        source = _current_s3()
        use_s3 = Confirm.ask("Keep the files in the company's S3 storage?", default=source is not None, console=console)
        if not use_s3:
            moved = _move(console, source, None)
            if moved == "failed":
                return
            upsert_env(ENV_PATH, "STORAGE", "disk")
            for name in _S3_SETTINGS:
                remove_env(ENV_PATH, name)
            console.print("Document files are kept on this server.")
            _restart(console, moved)
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
        moved = _move(console, source, config)
        if moved == "failed":
            return
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
        _restart(console, moved)


def _move(console: Console, source: S3Config | None, target: S3Config | None) -> Move:
    moved = offer_move(console, source, target)
    if moved == "failed":
        console.print("Nothing changed: run this step again to continue where the move stopped.")
    return moved


def _restart(console: Console, moved: Move) -> None:
    if moved == "moved in production":
        restart_production(console)
