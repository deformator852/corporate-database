import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values, load_dotenv

from exceptions import AppError

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE)

DOCUMENT_EVENTS_EXCHANGE = "document.events"
NOTIFICATION_EVENTS_EXCHANGE = "notification.events"

# APP_LANGUAGE → name used in the LLM system prompt.
LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "uk": "Ukrainian",
    "tr": "Turkish",
    "fr": "French",
}
DEFAULT_LANGUAGE = "en"


@dataclass(frozen=True, slots=True)
class EmbeddingSpec:
    hf_id: str
    dims: int
    query_prefix: str = ""
    passage_prefix: str = ""


_E5 = {"query_prefix": "query: ", "passage_prefix": "passage: "}
_BGE_EN = {"query_prefix": "Represent this sentence for searching relevant passages: "}
_SOLON = {"query_prefix": "query : "}

# EMBEDING_MODEL value → model spec.
EMBEDDING_MODELS = {
    "multilingual-e5-small": EmbeddingSpec("intfloat/multilingual-e5-small", 384, **_E5),
    "multilingual-e5-base": EmbeddingSpec("intfloat/multilingual-e5-base", 768, **_E5),
    "multilingual-e5-large": EmbeddingSpec("intfloat/multilingual-e5-large", 1024, **_E5),
    "bge-small-en": EmbeddingSpec("BAAI/bge-small-en-v1.5", 384, **_BGE_EN),
    "bge-base-en": EmbeddingSpec("BAAI/bge-base-en-v1.5", 768, **_BGE_EN),
    "bge-large-en": EmbeddingSpec("BAAI/bge-large-en-v1.5", 1024, **_BGE_EN),
    "solon-base": EmbeddingSpec("OrdalieTech/Solon-embeddings-base-0.1", 768, **_SOLON),
    "solon-large": EmbeddingSpec("OrdalieTech/Solon-embeddings-large-0.1", 1024, **_SOLON),
    "bge-m3": EmbeddingSpec("BAAI/bge-m3", 1024),
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


def language() -> str:
    value = (os.getenv("APP_LANGUAGE") or DEFAULT_LANGUAGE).strip()
    if value not in LANGUAGES:
        raise AppError(
            "misconfigured",
            "Unknown APP_LANGUAGE.",
            status_code=500,
        )
    return value


def embedding_model() -> EmbeddingSpec:
    spec = EMBEDDING_MODELS.get(_require("EMBEDING_MODEL"))
    if spec is None:
        raise AppError(
            "misconfigured",
            "Unknown embedding model.",
            status_code=500,
        )
    return spec


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
