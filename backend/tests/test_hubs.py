"""Live event hubs keep sending while clients come and go mid-broadcast."""

from conftest import run


class _Socket:
    def __init__(self, on_send=None) -> None:
        self.sent: list[dict] = []
        self.on_send = on_send

    async def accept(self) -> None:
        pass

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)
        if self.on_send:
            await self.on_send()


def test_a_client_connecting_during_a_broadcast_breaks_nothing():
    from services.documents.hub import DocumentHub
    from services.notifications.hub import NotificationHub

    documents = DocumentHub()
    newcomer = _Socket()
    first = _Socket(lambda: documents.connect(newcomer, ["standard"]))
    second = _Socket()

    async def scenario() -> None:
        await documents.connect(first, ["standard"])
        await documents.connect(second, ["standard"])
        await documents.broadcast({"id": 1, "classification": "standard"})

    run(scenario())
    assert second.sent == [{"id": 1, "classification": "standard"}]

    notifications = NotificationHub()
    tab_b = _Socket()
    tab_a = _Socket(lambda: notifications.connect(7, _Socket()))

    async def notify() -> None:
        await notifications.connect(7, tab_a)
        await notifications.connect(7, tab_b)
        await notifications.send(7, {"type": "document.completed"})

    run(notify())
    assert tab_a.sent and tab_b.sent


def test_event_consumers_restart_after_a_failure(monkeypatch):
    """RabbitMQ down at start, or restarted later: live updates resume."""
    import asyncio

    import main

    monkeypatch.setattr(main, "_RESTART_SECONDS", 0)
    attempts: list[int] = []

    async def consume() -> None:
        attempts.append(len(attempts))
        if len(attempts) < 3:
            raise ConnectionError("broker down")
        raise asyncio.CancelledError  # the backend stops

    async def scenario() -> None:
        try:
            await main.keep_running("Test events", consume)
        except asyncio.CancelledError:
            pass

    run(scenario())
    assert attempts == [0, 1, 2]
