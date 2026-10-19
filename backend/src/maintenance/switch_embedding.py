"""Rebuilds the search index for an embedding model: the step of
`uv run switch-embedding-model MODEL` (src/switch_embedding_model) that touches the data. In
production that command runs it inside the backend image:

    python -m maintenance.switch_embedding MODEL

Vectors of two models cannot be mixed, so every document is embedded again:
this drops the search index, queues every processed document and records
MODEL as the index's model. When the worker starts it processes them again
from their stored files, without "ready" notices; each document is found by
search again once it is done (the Documents page shows the progress). Chats,
documents and their files are not touched.

The backend and the worker must be stopped (switch-embedding-model stops them): they
would keep using the old model. Resumable: if it stops midway, run it again.
"""

import asyncio
import os
import sys
from collections.abc import Callable

from database import AsyncSessionLocal, engine
from exceptions import AppError
from services.search.embedding import EmbeddingModel
from services.search.index_model import rebuild_index, stored_index_model
from settings import EMBEDDING_MODELS


def load_model(model: str, report: Callable[[str], None] = print) -> None:
    """Makes `model` the configured one and loads it. Production runs
    offline, so it must already be on disk (switch-embedding-model downloads it)."""
    if model not in EMBEDDING_MODELS:
        raise AppError(
            "misconfigured",
            f"Unknown embedding model {model!r}. Choose one of: {', '.join(EMBEDDING_MODELS)}.",
            status_code=500,
        )
    os.environ["EMBEDDING_MODEL"] = model
    report(f"Loading {model}...")
    try:
        EmbeddingModel().warm_up()
    except Exception as exc:
        raise AppError(
            "unavailable",
            f"Could not load {model}: {exc}. Check the name and that it is downloaded.",
            status_code=503,
        ) from exc


async def switch(model: str, report: Callable[[str], None] = print) -> int:
    """Rebuilds the index for `model`; returns how many documents were queued."""
    # Before anything is dropped: a model that cannot load changes nothing.
    await asyncio.to_thread(load_model, model, report)
    async with AsyncSessionLocal() as session:
        previous = await stored_index_model(session)
        report(f"Index model: {previous or 'not recorded'} -> {model}")
        queued = await rebuild_index(session, model)
    report(f"{queued} document(s) queued; the worker embeds them with {model} when it starts.")
    return queued


async def main(model: str) -> None:
    try:
        await switch(model)
    except AppError as exc:
        raise SystemExit(f"Stopped: {exc.message}") from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: python -m maintenance.switch_embedding MODEL\nModels: {', '.join(EMBEDDING_MODELS)}")
    asyncio.run(main(sys.argv[1]))
