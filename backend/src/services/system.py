"""Health of the services Corpus depends on, for the admin status page.

Checks run in parallel, each with a timeout, so one hung service cannot hang
the page. Details are for operators: they may name hosts and models, never
secrets.
"""

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

from ollama import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.document import Document
from services.documents.rechunk import outdated_count
from services.search.embedding import get_embedding_model
from services.search.index_model import outdated_index_model
from services.search.rag import COLLECTION_NAME, Rag
from services.storage import ObjectStorage
from settings import (
    chunk_overlap,
    chunk_size,
    embedding_model,
    languages,
    llm_host,
    llm_model,
    llm_num_ctx,
)

CHECK_TIMEOUT_SECONDS = 4
Check = dict[str, Any]


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _ok(detail: str = "", **extra: Any) -> Check:
    return {"status": "ok", "detail": detail, **extra}


def _down(detail: str) -> Check:
    return {"status": "down", "detail": detail}


def _warning(detail: str, **extra: Any) -> Check:
    return {"status": "warning", "detail": detail, **extra}


async def _database(session: AsyncSession) -> Check:
    await session.execute(text("SELECT 1"))
    return _ok()


async def _search_index() -> Check:
    rag = Rag()
    try:
        if not await rag.client.collection_exists(COLLECTION_NAME):
            return _warning("Collection not created yet (no documents indexed).", chunks=0)
        info = await rag.client.get_collection(COLLECTION_NAME)
        chunks = info.points_count or 0
        return _ok(f"{_count(chunks, 'chunk')} indexed", chunks=chunks)
    finally:
        await rag.client.close()


def _storage(sample: str | None) -> Check:
    try:
        return _ok(ObjectStorage().check(sample))
    except AppError as exc:
        return _down(exc.message)


def _queue() -> Check:
    from worker import celery

    with celery.connection_or_acquire() as connection:
        waiting = connection.default_channel.queue_declare(queue="celery", passive=True).message_count
    replies = celery.control.inspect(timeout=2).ping() or {}
    workers = len(replies)
    if workers == 0:
        return _down("No worker is running: uploaded documents are not processed.") | {
            "workers": 0,
            "waiting": waiting,
        }
    return _ok(
        f"{_count(workers, 'worker')}, {_count(waiting, 'job')} waiting",
        workers=workers,
        waiting=waiting,
    )


async def _llm() -> Check:
    client = AsyncClient(host=llm_host(), timeout=CHECK_TIMEOUT_SECONDS)
    model = llm_model()
    installed = {m.model for m in (await client.list()).models if m.model}
    if model not in installed:
        return _down(f"Model {model} is not downloaded in Ollama.")
    loaded = {m.model for m in (await client.ps()).models if m.model}
    if model not in loaded:
        return _warning(f"{model} is not loaded yet; the first answer will be slow.")
    return _ok(f"{model} loaded")


def _embedder() -> Check:
    spec = embedding_model()
    if get_embedding_model().loaded:
        return _ok(spec.hf_id)
    return _warning(f"{spec.hf_id} is not loaded yet; the first question will be slow.")


def _disk() -> Check:
    usage = shutil.disk_usage("/")
    free = usage.free / usage.total
    detail = f"{usage.free / 1024**3:.1f} GB free of {usage.total / 1024**3:.1f} GB"
    return _warning(detail) if free < 0.1 else _ok(detail)


async def _run(name: str, check: Callable[[], Awaitable[Check]]) -> Check:
    try:
        result = await asyncio.wait_for(check(), CHECK_TIMEOUT_SECONDS + 1)
    except TimeoutError:
        result = _down("No answer in time.")
    except Exception as exc:  # noqa: BLE001 - any failure is a status, not a crash
        result = _down(f"{type(exc).__name__}: {str(exc)[:160]}")
    return {"name": name, **result}


def _thread(check: Callable[[], Check]) -> Callable[[], Awaitable[Check]]:
    return lambda: asyncio.to_thread(check)


async def _sample_file(session: AsyncSession) -> str | None:
    """The newest document's file key, for the storage check; None without
    documents, or with the database down (its own check says so)."""
    try:
        return await session.scalar(select(Document.object_key).order_by(Document.id.desc()).limit(1))
    except Exception:  # noqa: BLE001 - the database check reports it
        await session.rollback()
        return None


async def system_status(session: AsyncSession) -> dict[str, Any]:
    sample = await _sample_file(session)
    services = await asyncio.gather(
        _run("database", lambda: _database(session)),
        _run("search_index", _search_index),
        _run("storage", _thread(lambda: _storage(sample))),
        _run("queue", _thread(_queue)),
        _run("llm", _llm),
        _run("embedding", _thread(_embedder)),
        _run("disk", _thread(_disk)),
    )
    rows = await session.execute(select(Document.status, func.count()).group_by(Document.status))
    documents = dict(rows.tuples().all())
    spec = embedding_model()
    return {
        "services": services,
        "documents": {str(status): count for status, count in documents.items()},
        "config": {
            # The default first; several when users switch in the header.
            "languages": list(languages()),
            "llm_model": llm_model(),
            "llm_context": llm_num_ctx(),
            "embedding_model": spec.hf_id,
            "chunk_size": chunk_size(),
            "chunk_overlap": chunk_overlap(),
        },
        # Completed documents cut with another chunk size or overlap.
        "outdated_chunks": await outdated_count(session),
        # Documents with no file in the storage, as of the backend's start.
        "missing_files": await session.scalar(
            select(func.count()).select_from(Document).where(Document.file_missing.is_(True))
        ),
        # The model the index is built with when EMBEDDING_MODEL names
        # another: search is off until it is rebuilt.
        "outdated_index_model": await outdated_index_model(session),
    }
