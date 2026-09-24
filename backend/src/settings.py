import os
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values, load_dotenv

from exceptions import AppError

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE)

DOCUMENT_EVENTS_EXCHANGE = "document.events"
NOTIFICATION_EVENTS_EXCHANGE = "notification.events"

EMBEDING_MODEL_ENV_TO_HUGGINGFACE_ID = {
    "multilingual-e5-small": "intfloat/multilingual-e5-small",
    "multilingual-e5-base": "intfloat/multilingual-e5-base",
    "multilingual-e5-large": "intfloat/multilingual-e5-large",
}

# Substring in the resolved model id → Qdrant vector dimension.
EMBEDDING_MODEL_VARIANT_VECTOR_SIZE = {
    "e5-small": 384,
    "e5-base": 768,
    "e5-large": 1024,
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
    return EMBEDING_MODEL_ENV_TO_HUGGINGFACE_ID.get(raw, raw)


def embedding_vector_size() -> int:
    model = embedding_model_id().lower()
    for suffix, size in EMBEDDING_MODEL_VARIANT_VECTOR_SIZE.items():
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


def llm_host() -> str:
    return (os.getenv("LLM_HOST") or "http://127.0.0.1:11434").strip()


def llm_model() -> str:
    value = (
        dotenv_values(ENV_FILE).get("LLM_MODEL") or os.getenv("LLM_MODEL") or ""
    ).strip()
    if not value:
        raise AppError(
            "misconfigured",
            "LLM_MODEL is not configured.",
            status_code=500,
        )
    return value
