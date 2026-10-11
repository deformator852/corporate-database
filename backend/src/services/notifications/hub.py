from fastapi import WebSocket


class NotificationHub:
    def __init__(self) -> None:
        self._clients: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        clients = self._clients.get(user_id)
        if clients is None:
            return
        clients.discard(websocket)
        if not clients:
            del self._clients[user_id]

    async def send(self, user_id: int, payload: dict) -> None:
        stale: list[WebSocket] = []
        # A copy: tabs connect and leave while a send is awaited.
        for client in list(self._clients.get(user_id, ())):
            try:
                await client.send_json(payload)
            except Exception:
                stale.append(client)
        for client in stale:
            self.disconnect(user_id, client)


hub = NotificationHub()


async def dispatch_notification(payload: dict) -> None:
    user_id = payload.get("user_id")
    if isinstance(user_id, int):
        await hub.send(user_id, payload)
