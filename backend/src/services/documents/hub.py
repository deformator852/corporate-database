from collections.abc import Iterable

from fastapi import WebSocket


class DocumentHub:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, frozenset[str]] = {}

    async def connect(self, websocket: WebSocket, classifications: Iterable[str]) -> None:
        await websocket.accept()
        self._clients[websocket] = frozenset(classifications)

    def update(self, websocket: WebSocket, classifications: Iterable[str]) -> None:
        if websocket in self._clients:
            self._clients[websocket] = frozenset(classifications)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.pop(websocket, None)

    async def broadcast(self, payload: dict) -> None:
        classification = payload.get("classification") or "standard"
        stale: list[WebSocket] = []
        # A copy: clients connect and leave while a send is awaited.
        for client, allowed in list(self._clients.items()):
            if classification not in allowed:
                continue
            try:
                await client.send_json(payload)
            except Exception:
                stale.append(client)
        for client in stale:
            self.disconnect(client)


hub = DocumentHub()
