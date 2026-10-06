"""Stand-ins for the services around Corpus, so tests run the real code up to
the network boundary: MinIO (a dict), Qdrant (its own in-memory mode, real
filters and search), the embedding model (word-hash vectors: shared words =
similar), Ollama (scripted answers), RabbitMQ (in-process fanout that also
reaches the TestClient's event loop) and Celery (records queued jobs)."""

import asyncio
import io
import json
import re
import zlib
from collections import defaultdict
from contextlib import asynccontextmanager
from types import SimpleNamespace

import numpy as np
from minio.error import S3Error
from ollama import ResponseError
from qdrant_client import AsyncQdrantClient


def s3_error(code: str) -> S3Error:
    return S3Error(None, code, code, "resource", "request", "host")


class FakeMinio:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_with: str | None = None  # S3 error code for every call

    def _check(self) -> None:
        if self.fail_with:
            raise s3_error(self.fail_with)

    def put_object(self, bucket, key, data, length, content_type=None):
        self._check()
        self.objects[key] = data.read()

    def get_object(self, bucket, key):
        self._check()
        if key not in self.objects:
            raise s3_error("NoSuchKey")
        body = io.BytesIO(self.objects[key])
        return SimpleNamespace(read=body.read, close=lambda: None, release_conn=lambda: None)

    def remove_object(self, bucket, key):
        self._check()
        if key not in self.objects:
            raise s3_error("NoSuchKey")
        del self.objects[key]

    def stat_object(self, bucket, key):
        self._check()
        if key not in self.objects:
            raise s3_error("NoSuchKey")


class SharedQdrant:
    """One in-memory Qdrant for the whole test; `close()` keeps the data."""

    def __init__(self) -> None:
        self._client = AsyncQdrantClient(location=":memory:")

    def __getattr__(self, name):
        return getattr(self._client, name)

    async def close(self) -> None:
        return None


_WORD = re.compile(r"\w+")


class FakeSentenceTransformer:
    """Bag of hashed words, normalized: texts sharing words are close."""

    dims = 384

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    def encode(self, texts, normalize_embeddings=True):
        vectors = np.zeros((len(texts), self.dims), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in _WORD.findall(text.lower()):
                if word in {"query", "passage"}:
                    continue
                vectors[row, zlib.crc32(word.encode()) % self.dims] += 1.0
            norm = np.linalg.norm(vectors[row])
            vectors[row] = vectors[row] / norm if norm else vectors[row]
            if not norm:
                vectors[row, 0] = 1.0
        return vectors


class FakeOllama:
    """Scripted Ollama. `answer` streams in pieces for chat; `error` raises
    on every call."""

    def __init__(self) -> None:
        self.answer = "The travel budget is 500 EUR."
        # Seconds before each streamed piece: a slow model.
        self.delay = 0.0
        self.error: Exception | None = None
        self.installed = {"llama3.1:8b"}
        self.loaded: set[str] = set()
        self.calls: list[dict] = []

    def client(self, *args, **kwargs) -> FakeOllama:
        return self

    async def chat(self, *, model, messages, stream=False, **kwargs):
        self.calls.append({"model": model, "messages": messages, "stream": stream, **kwargs})
        if self.error is not None:
            raise self.error
        return self._stream(self.answer)

    async def _stream(self, text: str):
        for piece in re.findall(r"\S+\s*", text):
            await asyncio.sleep(self.delay)
            yield SimpleNamespace(message=SimpleNamespace(content=piece))

    async def generate(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.loaded.add(kwargs["model"])

    async def list(self):
        return SimpleNamespace(models=[SimpleNamespace(model=m) for m in self.installed])

    async def ps(self):
        return SimpleNamespace(models=[SimpleNamespace(model=m) for m in self.loaded])


def model_missing() -> ResponseError:
    return ResponseError("model not found", 404)


class FakeBroker:
    """Fanout exchanges in memory. Consumers may live on another event loop
    (the TestClient's); messages reach them thread-safely."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []
        self._queues: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(list)

    async def connect_robust(self, url: str) -> _Connection:
        return _Connection(self)

    def events(self, exchange: str) -> list[dict]:
        return [payload for name, payload in self.published if name == exchange]

    def _publish(self, exchange: str, body: bytes) -> None:
        self.published.append((exchange, json.loads(body)))
        for loop, queue in list(self._queues[exchange]):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, body)
            except RuntimeError:  # that loop is closed
                self._queues[exchange].remove((loop, queue))


class _Connection:
    def __init__(self, broker: FakeBroker) -> None:
        self.broker = broker
        self.is_closed = False

    async def channel(self) -> _Channel:
        return _Channel(self.broker)

    async def close(self) -> None:
        self.is_closed = True


class _Channel:
    def __init__(self, broker: FakeBroker) -> None:
        self.broker = broker

    async def declare_exchange(self, name, *args, **kwargs):
        broker = self.broker
        return SimpleNamespace(
            name=name,
            publish=lambda message, routing_key="": _async(broker._publish(name, message.body)),
        )

    async def declare_queue(self, **kwargs) -> _Queue:
        return _Queue(self.broker)

    async def close(self) -> None:
        return None


async def _async(value=None):
    return value


class _Queue:
    def __init__(self, broker: FakeBroker) -> None:
        self.broker = broker
        self.queue: asyncio.Queue = asyncio.Queue()

    async def bind(self, exchange) -> None:
        self.broker._queues[exchange.name].append((asyncio.get_running_loop(), self.queue))

    @asynccontextmanager
    async def iterator(self):
        async def messages():
            while True:
                body = await self.queue.get()
                yield SimpleNamespace(body=body, process=_processed)

        yield messages()


@asynccontextmanager
async def _processed():
    yield


class RecordingQueue:
    """Celery stand-in: remembers which documents were queued."""

    def __init__(self) -> None:
        self.ids: list[int] = []
        self.fail = False

    def enqueue(self, document_id: int) -> None:
        if self.fail:
            raise ConnectionError("broker down")
        self.ids.append(document_id)
