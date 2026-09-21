import os
from urllib.parse import quote

from dotenv import load_dotenv

from exceptions import AppError

load_dotenv()

DOCUMENT_EVENTS_EXCHANGE = "document.events"
NOTIFICATION_EVENTS_EXCHANGE = "notification.events"

_E5_SIZES = {
    "e5-small": 384,
    "e5-base": 768,
    "e5-large": 1024,
}

_E5_IDS = {
    "multilingual-e5-small": "intfloat/multilingual-e5-small",
    "multilingual-e5-base": "intfloat/multilingual-e5-base",
    "multilingual-e5-large": "intfloat/multilingual-e5-large",
}


def _require(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise AppError(
            "misconfigured",
            f"{name} is not configured.",
            status_code=500,
        )
    return value


def embedding_model_id() -> str:
    raw = _require("EMBEDING_MODEL")
    return _E5_IDS.get(raw, raw)


def embedding_vector_size() -> int:
    model = embedding_model_id().lower()
    for suffix, size in _E5_SIZES.items():
        if suffix in model:
            return size
    raise AppError(
        "misconfigured",
        "Unknown embedding model.",
        status_code=500,
    )


def rabbitmq_url() -> str:
    user = quote(_require("RABBITMQ_USER"), safe="")
    password = quote(_require("RABBITMQ_PASSWORD"), safe="")
    host = _require("RABBITMQ_HOST")
    port = os.getenv("RABBITMQ_PORT") or "5672"
    return f"amqp://{user}:{password}@{host}:{port}//"


def minio_endpoint() -> str:
    return _require("MINIO_ENDPOINT")


def minio_access_key() -> str:
    return _require("MINIO_ACCESS_KEY")


def minio_secret_key() -> str:
    return _require("MINIO_SECRET_KEY")


def minio_bucket() -> str:
    return os.getenv("MINIO_BUCKET") or "documents"


def minio_secure() -> bool:
    return (os.getenv("MINIO_SECURE") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }
