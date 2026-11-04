"""Copies the document files from one storage to another: the step of
`uv run configure` (Document storage) that moves them when STORAGE changes.
In production that command runs it inside the backend image, which sees
both the documents_data volume and the S3 storage (through s3-tunnel):

    python -m maintenance.move_files

The source is the storage the environment configures (STORAGE, S3_*), the
target the one TARGET_STORAGE, TARGET_STORAGE_DIR and TARGET_S3_* name.

The files are encrypted already and keep their keys, so moving is copying.
Each copy is read back before the next file. The originals stay: delete
them once Archfold works with the new storage. Resumable: a file already in
the target is not copied again.
"""

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from database import AsyncSessionLocal, engine
from exceptions import AppError
from models.document import Document
from services.storage import DiskStore, FileStore, S3Store, file_store
from settings import S3Config, storage_dir


@dataclass(frozen=True, slots=True)
class Moved:
    copied: int
    # In the target already: an earlier run copied them.
    present: int
    # Not in the source either: shown as missing on the Documents page.
    missing: int


async def document_keys() -> list[str]:
    """The keys of every document's file: the database lists them, the S3
    account may not (it has no s3:ListBucket)."""
    try:
        async with AsyncSessionLocal() as session:
            return list(await session.scalars(select(Document.object_key).order_by(Document.id)))
    finally:
        await engine.dispose()


def move(keys: list[str], source: FileStore, target: FileStore, report: Callable[[str], None] = print) -> Moved:
    copied = present = missing = 0
    for number, key in enumerate(keys, start=1):
        if target.exists(key):
            present += 1
            continue
        try:
            data = source.read(key)
        except AppError as exc:
            if exc.code != "not_found":
                raise
            missing += 1
            continue
        target.write(key, data)
        if target.read(key) != data:
            raise AppError("misconfigured", f"The new storage returned other data for {key}.", status_code=500)
        copied += 1
        if number % 100 == 0:
            report(f"{number} of {len(keys)} files...")
    return Moved(copied, present, missing)


def summary(moved: Moved) -> str:
    text = f"{moved.copied} file(s) copied, {moved.present} already there."
    if moved.missing:
        text += f" {moved.missing} missing from the old storage too: the Documents page marks them."
    return text


def target_store() -> FileStore:
    if os.environ["TARGET_STORAGE"] == "disk":
        return DiskStore(Path(os.getenv("TARGET_STORAGE_DIR") or storage_dir()))
    return S3Store(
        S3Config(
            endpoint=os.environ["TARGET_S3_ENDPOINT"],
            bucket=os.environ["TARGET_S3_BUCKET"],
            access_key=os.environ["TARGET_S3_ACCESS_KEY"],
            secret_key=os.environ["TARGET_S3_SECRET_KEY"],
            region=os.getenv("TARGET_S3_REGION") or "us-east-1",
            cacert=os.getenv("TARGET_S3_CACERT") or "",
            connect=os.getenv("TARGET_S3_CONNECT") or "",
        )
    )


def main() -> None:
    keys = asyncio.run(document_keys())
    print(f"Moving the files of {len(keys)} document(s)...")
    try:
        print(summary(move(keys, file_store(), target_store())))
    except AppError as exc:
        raise SystemExit(f"Stopped: {exc.message} {exc.__cause__ or ''}".strip()) from None


if __name__ == "__main__":
    main()
