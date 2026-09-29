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


def qdrant_api_key() -> str:
    return _require("QDRANT_API_KEY")


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


def minio_region() -> str:
    """Passing the region stops the client from asking the server for the
    bucket location before every call, which the least-privilege app user is
    not allowed to do (AccessDenied)."""
    return (os.getenv("MINIO_REGION") or "us-east-1").strip()


def minio_secure() -> bool:
    return (os.getenv("MINIO_SECURE") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def llm_host() -> str:
    return (os.getenv("LLM_HOST") or "http://127.0.0.1:11434").strip()


def llm_num_ctx() -> int:
    """Fixed LLM context size in tokens. Ollama reloads the model whenever
    num_ctx changes between requests, so it must not vary per question."""
    raw = (os.getenv("LLM_NUM_CTX") or "16384").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise AppError(
            "misconfigured", "LLM_NUM_CTX must be a number.", status_code=500
        ) from exc
    if value < 4096:
        raise AppError(
            "misconfigured", "LLM_NUM_CTX must be at least 4096.", status_code=500
        )
    return value


# Chunk size and overlap in characters; see setup/steps/chunking.py for what
# each size is good at.
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 150
MIN_CHUNK_SIZE = 200
MAX_CHUNK_SIZE = 4000


def _live_int(name: str, default: int) -> int:
    # Read from .env per call: a change applies to the next upload without a
    # worker restart.
    raw = (dotenv_values(ENV_FILE).get(name) or os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise AppError(
            "misconfigured", f"{name} must be a number.", status_code=500
        ) from exc


def chunk_size() -> int:
    value = _live_int("CHUNK_SIZE", DEFAULT_CHUNK_SIZE)
    if not MIN_CHUNK_SIZE <= value <= MAX_CHUNK_SIZE:
        raise AppError(
            "misconfigured",
            f"CHUNK_SIZE must be {MIN_CHUNK_SIZE}-{MAX_CHUNK_SIZE}.",
            status_code=500,
        )
    return value


def chunk_overlap() -> int:
    """At most half the chunk: beyond that every piece of text is stored and
    embedded twice or more."""
    value = _live_int("CHUNK_OVERLAP", DEFAULT_CHUNK_OVERLAP)
    if not 0 <= value <= chunk_size() // 2:
        raise AppError(
            "misconfigured",
            "CHUNK_OVERLAP must be between 0 and half of CHUNK_SIZE.",
            status_code=500,
        )
    return value


def chat_retention_days() -> int:
    """Saved chats idle this long are deleted; 0 keeps them forever."""
    return max(0, _live_int("CHAT_RETENTION_DAYS", 90))


TEXT_CLEANUP_MODES = ("llm", "rules", "off")


def text_cleanup_mode() -> str:
    """How chunks are cleaned before embedding: rules and then the LLM, rules
    only, or not at all. Read per document, so a change applies to the next
    upload without restarting the worker."""
    value = (
        dotenv_values(ENV_FILE).get("TEXT_CLEANUP") or os.getenv("TEXT_CLEANUP") or "llm"
    ).strip()
    if value not in TEXT_CLEANUP_MODES:
        raise AppError(
            "misconfigured",
            "TEXT_CLEANUP must be llm, rules or off.",
            status_code=500,
        )
    return value


def text_cleanup_budget_seconds() -> int:
    """LLM cleanup time per document. Chunks past it get rules only, so large
    files still finish inside the worker's time limit."""
    raw = (os.getenv("TEXT_CLEANUP_BUDGET_SECONDS") or "480").strip()
    try:
        return max(0, int(raw))
    except ValueError as exc:
        raise AppError(
            "misconfigured",
            "TEXT_CLEANUP_BUDGET_SECONDS must be a number.",
            status_code=500,
        ) from exc


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
