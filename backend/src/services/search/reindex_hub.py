"""Live progress of an embedding model switch, for the banner every signed-in
user sees (frontend widgets/reindex-banner). A socket gets the current
progress when it connects, then each change: the worker's document events
(services/documents/events.py) say a document moved on, and the backend
counts again. A percentage, not counts: those would tell how many documents
exist above a user's clearance."""

import logging

from fastapi import WebSocket

from database import AsyncSessionLocal
from services.search.index_model import reindex_progress

logger = logging.getLogger(__name__)


async def current_progress() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        progress = await reindex_progress(session)
    return {"active": progress.active, "percent": progress.percent}


class ReindexHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._last: dict[str, object] | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        await websocket.send_json(await current_progress())

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def refresh(self) -> None:
        """After a document event: sends the progress when it changed. Never
        raises: it runs in the loop that also feeds the documents list."""
        if not self._clients:
            return
        try:
            progress = await current_progress()
        except Exception:  # noqa: BLE001 - the banner waits for the next event
            logger.warning("Could not count the reindexing progress", exc_info=True)
            return
        # Ordinary uploads also send events: "no switch running" goes out once.
        if not progress["active"] and self._last is not None and not self._last["active"]:
            return
        self._last = progress
        for client in list(self._clients):
            try:
                await client.send_json(progress)
            except Exception:  # noqa: BLE001 - a closed socket, whatever the server says
                self.disconnect(client)


reindex_hub = ReindexHub()
