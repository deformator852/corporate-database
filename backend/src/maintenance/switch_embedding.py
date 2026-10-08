"""Switches the search index to another embedding model, or rebuilds it with
the current one (e.g. after changing CHUNK_SIZE).

    deploy/deploy.sh switch-model MODEL                                      (production)
    cd backend/src && uv run python -m maintenance.switch_embedding MODEL    (development)

Vectors of two models cannot be mixed, so every document is embedded again:
this drops the search index, queues every processed document and records
MODEL as the index's model. When the worker starts it processes them again
from their stored files, without "ready" notices; each document is found by
search again once it is done (the Documents page shows the progress). Chats,
documents and their files are not touched.

Stop the backend and the worker first (deploy.sh does): they would keep
using the old model. In development this also writes EMBEDDING_MODEL to
backend/.env; production keeps .env outside the container, so deploy.sh
writes it. Resumable: if it stops midway, run it again.
"""

import asyncio
import os
import sys
from collections.abc import Callable
from typing import cast

from sqlalchemy import CursorResult, update

from database import AsyncSessionLocal, engine
from exceptions import AppError
from models.document import Document, DocumentStatus
from services.search.embedding import EmbeddingModel
from services.search.index_model import save_index_model, stored_index_model
from services.search.rag import COLLECTION_NAME, Rag
from settings import EMBEDDING_MODELS


async def switch(model: str, report: Callable[[str], None] = print) -> int:
    """Rebuilds the index for `model`; returns how many documents were queued."""
    if model not in EMBEDDING_MODELS:
        raise AppError(
            "misconfigured",
            f"Unknown embedding model {model!r}. Choose one of: {', '.join(EMBEDDING_MODELS)}.",
            status_code=500,
        )
    os.environ["EMBEDDING_MODEL"] = model
    # Before anything is dropped: production runs offline, so the model must
    # already be on disk (deploy.sh downloads it first).
    report(f"Loading {model}...")
    try:
        await asyncio.to_thread(EmbeddingModel().warm_up)
    except Exception as exc:
        raise AppError(
            "unavailable",
            f"Could not load {model}: {exc}. Download it first (deploy/deploy.sh models).",
            status_code=503,
        ) from exc
    async with AsyncSessionLocal() as session:
        previous = await stored_index_model(session)
    report(f"Index model: {previous or 'not recorded'} -> {model}")

    rag = Rag()
    try:
        if await rag.client.collection_exists(COLLECTION_NAME):
            await rag.client.delete_collection(COLLECTION_NAME)
            report("Old search index deleted.")
    finally:
        await rag.client.close()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Document)
            .where(Document.status == DocumentStatus.COMPLETED)
            .values(status=DocumentStatus.QUEUED, progress=0, reindexing=True, ready_unannounced=False)
        )
        await session.commit()
        # An UPDATE gives a CursorResult; the async API types it as Result.
        queued = cast(CursorResult, result).rowcount or 0
        # Last: until here a rerun repeats every step.
        await save_index_model(session, model, queued=queued)
    report(f"{queued} document(s) queued; the worker embeds them with {model} when it starts.")
    return queued


def _write_env(model: str) -> None:
    """Development: backend/.env sits next to the code."""
    from setup.env import ENV_PATH, upsert_env

    if ENV_PATH.exists():
        upsert_env(ENV_PATH, "EMBEDDING_MODEL", model)
        print(f"Wrote EMBEDDING_MODEL={model} to {ENV_PATH}")


async def main(model: str) -> None:
    try:
        await switch(model)
    except AppError as exc:
        raise SystemExit(f"Stopped: {exc.message}") from None
    finally:
        await engine.dispose()
    _write_env(model)
    print("Start the backend and the worker again.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: python -m maintenance.switch_embedding MODEL\nModels: {', '.join(EMBEDDING_MODELS)}")
    asyncio.run(main(sys.argv[1]))
