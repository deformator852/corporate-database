import logging
import os
from dataclasses import dataclass
from functools import partial
from importlib.metadata import version
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values, load_dotenv

from exceptions import AppError

# Development: backend/.env. Production: compose passes the values as
# environment variables. Either way they are read once per process start;
# after changing .env (uv run configure), restart the backend and the worker.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
# The names .env set (not set in the environment before): the commands that
# start Docker Compose leave them out (switch_embedding_model.stack_env).
FROM_ENV_FILE = frozenset(name for name in dotenv_values(ENV_FILE) if name not in os.environ)
load_dotenv(ENV_FILE)

# The Hub answers anonymous downloads with an "unauthenticated requests"
# notice (X-HF-Warning) that huggingface_hub logs as a warning; public models
# need no token, so it would only fill the console and the error log.
logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)

DOCUMENT_EVENTS_EXCHANGE = "document.events"
NOTIFICATION_EVENTS_EXCHANGE = "notification.events"

# Language code → name used in the LLM system prompt.
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
    # Search hits scoring lower are not relevant: the chat neither uses nor
    # lists them. Scores differ per model, so each is calibrated with
    # evals/search_relevance.py; None turns the filter off.
    min_score: float | None = None


_e5 = partial(EmbeddingSpec, query_prefix="query: ", passage_prefix="passage: ")
_bge_en = partial(EmbeddingSpec, query_prefix="Represent this sentence for searching relevant passages: ")
_solon = partial(EmbeddingSpec, query_prefix="query : ")

# EMBEDDING_MODEL value → model spec. min_score: calibrated with
# evals/search_relevance.py on evals/dataset.LANG.json (and dataset_long.en.json
# for English models: the lower of its values at chunks of 400 and 800).
EMBEDDING_MODELS = {
    "multilingual-e5-small": _e5("intfloat/multilingual-e5-small", 384, min_score=0.81),
    "multilingual-e5-base": _e5("intfloat/multilingual-e5-base", 768, min_score=0.785),
    "multilingual-e5-large": _e5("intfloat/multilingual-e5-large", 1024),
    "bge-small-en": _bge_en("BAAI/bge-small-en-v1.5", 384, min_score=0.54),
    "bge-base-en": _bge_en("BAAI/bge-base-en-v1.5", 768, min_score=0.48),
    "bge-large-en": _bge_en("BAAI/bge-large-en-v1.5", 1024, min_score=0.525),
    "solon-base": _solon("OrdalieTech/Solon-embeddings-base-0.1", 768, min_score=0.375),
    "solon-large": _solon("OrdalieTech/Solon-embeddings-large-0.1", 1024, min_score=0.39),
    "bge-m3": EmbeddingSpec("BAAI/bge-m3", 1024, min_score=0.45),
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


def languages() -> tuple[str, ...]:
    """APP_LANGUAGES: the languages users switch between, the default
    (APP_LANGUAGE) first. Unset: only the default."""
    default = language()
    codes = [code.strip() for code in (os.getenv("APP_LANGUAGES") or "").split(",") if code.strip()]
    if any(code not in LANGUAGES for code in codes):
        raise AppError(
            "misconfigured",
            "Unknown language in APP_LANGUAGES.",
            status_code=500,
        )
    return tuple(dict.fromkeys([default, *codes]))


def embedding_model_key() -> str:
    """EMBEDDING_MODEL, one of EMBEDDING_MODELS."""
    key = _require("EMBEDDING_MODEL")
    if key not in EMBEDDING_MODELS:
        raise AppError(
            "misconfigured",
            "Unknown embedding model.",
            status_code=500,
        )
    return key


def embedding_model() -> EmbeddingSpec:
    return EMBEDDING_MODELS[embedding_model_key()]


def qdrant_api_key() -> str:
    return _require("QDRANT_API_KEY")


def rabbitmq_url() -> str:
    user = quote(_require("RABBITMQ_USER"), safe="")
    password = quote(_require("RABBITMQ_PASSWORD"), safe="")
    host = _require("RABBITMQ_HOST")
    port = os.getenv("RABBITMQ_PORT") or "5672"
    return f"amqp://{user}:{password}@{host}:{port}//"


# Where document files are kept (services/storage.py).
STORAGES = ("disk", "s3")


def storage() -> str:
    """disk (default): on this server. s3: the company's own S3 storage."""
    kind = (os.getenv("STORAGE") or "disk").strip().lower()
    if kind not in STORAGES:
        raise AppError("misconfigured", "STORAGE must be disk or s3.", status_code=500)
    return kind


def storage_dir() -> Path:
    """STORAGE=disk: the folder of the files. Production sets it to the
    documents_data volume; development keeps them in backend/storage."""
    folder = Path((os.getenv("STORAGE_DIR") or "storage").strip())
    return folder if folder.is_absolute() else ENV_FILE.parent / folder


@dataclass(frozen=True, slots=True)
class S3Config:
    """STORAGE=s3: the company's S3-compatible object storage (Ceph, NetApp
    StorageGRID, Dell ECS, AWS S3 and the like). The bucket is the company's:
    Archfold only reads, writes and deletes objects in it."""

    # http(s)://host[:port], no path.
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    # Passed on every call: otherwise the client asks for the bucket's
    # location first, which a least-privilege account may not do.
    region: str = "us-east-1"
    # CA file of the storage's certificate when a company CA signed it.
    cacert: str = ""
    # host:port to dial instead of the endpoint's host, with TLS still
    # checked against the endpoint's name: production's s3-tunnel, the only
    # way out of the internal network.
    connect: str = ""


def s3_config() -> S3Config:
    endpoint = _require("S3_ENDPOINT").rstrip("/")
    if not endpoint.startswith(("https://", "http://")) or endpoint.count("/") > 2:
        raise AppError(
            "misconfigured", "S3_ENDPOINT must be an http(s)://host[:port] address, no path.", status_code=500
        )
    return S3Config(
        endpoint=endpoint,
        bucket=_require("S3_BUCKET"),
        access_key=_require("S3_ACCESS_KEY"),
        secret_key=_require("S3_SECRET_KEY"),
        region=(os.getenv("S3_REGION") or "us-east-1").strip(),
        cacert=(os.getenv("S3_CACERT") or "").strip(),
        connect=(os.getenv("S3_CONNECT") or "").strip(),
    )


def llm_host() -> str:
    return (os.getenv("LLM_HOST") or "http://127.0.0.1:11434").strip()


def llm_num_ctx() -> int:
    """Fixed LLM context size in tokens. Ollama reloads the model whenever
    num_ctx changes between requests, so it must not vary per question."""
    raw = (os.getenv("LLM_NUM_CTX") or "16384").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise AppError("misconfigured", "LLM_NUM_CTX must be a number.", status_code=500) from exc
    if value < 4096:
        raise AppError("misconfigured", "LLM_NUM_CTX must be at least 4096.", status_code=500)
    return value


# Chunk size and overlap in characters; see setup/steps/chunking.py for what
# each size is good at.
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 150
MIN_CHUNK_SIZE = 200
MAX_CHUNK_SIZE = 4000


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise AppError("misconfigured", f"{name} must be a number.", status_code=500) from exc


def chunk_size() -> int:
    value = _int_env("CHUNK_SIZE", DEFAULT_CHUNK_SIZE)
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
    value = _int_env("CHUNK_OVERLAP", DEFAULT_CHUNK_OVERLAP)
    if not 0 <= value <= chunk_size() // 2:
        raise AppError(
            "misconfigured",
            "CHUNK_OVERLAP must be between 0 and half of CHUNK_SIZE.",
            status_code=500,
        )
    return value


def chat_retention_days() -> int:
    """Saved chats idle this long are deleted; 0 keeps them forever."""
    return max(0, _int_env("CHAT_RETENTION_DAYS", 90))


def error_log_retention_days() -> int:
    """Error log entries older than this are deleted; 0 keeps them forever."""
    return max(0, _int_env("ERROR_LOG_RETENTION_DAYS", 30))


DEFAULT_CHAT_QUESTIONS = 20


def chat_questions_per_10_min() -> int:
    """Questions one user may ask in any 10 minutes; 0 = no limit."""
    return max(0, _int_env("CHAT_QUESTIONS_PER_10_MIN", DEFAULT_CHAT_QUESTIONS))


# Answers the LLM writes at the same time (Ollama's OLLAMA_NUM_PARALLEL; set
# in compose from LLM_PARALLEL). Each one reserves its own context memory.
DEFAULT_LLM_PARALLEL = 4
MAX_LLM_PARALLEL = 16


TEXT_CLEANUP_MODES = ("rules", "off")


def text_cleanup_mode() -> str:
    """How chunks are cleaned before embedding: by rules, or not at all."""
    value = (os.getenv("TEXT_CLEANUP") or "rules").strip()
    if value not in TEXT_CLEANUP_MODES:
        raise AppError(
            "misconfigured",
            "TEXT_CLEANUP must be rules or off.",
            status_code=500,
        )
    return value


def app_version() -> str:
    """Archfold's version: `version` in backend/pyproject.toml, the one place
    it is set (see CHANGELOG.md)."""
    return version("backend")


def built_with_llama() -> bool:
    """LLM_MODEL is a Meta Llama model, whose license asks a product built
    with it to show "Built with Llama"."""
    return (os.getenv("LLM_MODEL") or "").strip().lower().rsplit("/", 1)[-1].startswith("llama")


def llm_model() -> str:
    value = (os.getenv("LLM_MODEL") or "").strip()
    if not value:
        raise AppError(
            "misconfigured",
            "LLM_MODEL is not configured.",
            status_code=500,
        )
    return value


def _flag(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    return default if not raw else raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class OidcConfig:
    """Single sign-on with the company's identity provider (OpenID Connect):
    Microsoft Entra ID, ADFS, Keycloak, Okta and the like."""

    issuer: str
    client_id: str
    client_secret: str
    # This server's callback, as registered at the provider:
    # https://SITE/api/v1/auth/sso/callback.
    redirect_uri: str
    # Shown on the sign-in button: "Sign in with NAME".
    name: str
    # ID token claim listing the user's groups.
    groups_claim: str
    # Provider group -> Archfold role key. Mapped roles follow the groups at
    # every sign-in; other roles stay as administrators set them.
    role_map: dict[str, str]
    # A first SSO sign-in takes over the Archfold account with the same email.
    link_by_email: bool
    # host:port to dial instead of the issuer's host, with TLS still checked
    # against the issuer's name: production's sso-tunnel, the backend's only
    # way out of the internal network.
    connect: str = ""
    # CA file of the provider's certificate when a company CA signed it.
    cacert: str = ""


def _role_map(raw: str) -> dict[str, str]:
    """`group=role;group=role`. Split at the last `=`: group names may hold
    one (LDAP DNs: CN=Legal,OU=Groups,DC=acme)."""
    pairs = (pair.rpartition("=") for pair in raw.split(";") if pair.strip())
    return {group.strip(): role.strip() for group, _, role in pairs if group.strip() and role.strip()}


def oidc_config() -> OidcConfig | None:
    """None while OIDC_ISSUER is unset: SSO is off."""
    issuer = (os.getenv("OIDC_ISSUER") or "").strip().rstrip("/")
    if not issuer:
        return None
    if not issuer.startswith("https://"):
        raise AppError("misconfigured", "OIDC_ISSUER must be an https:// address.", status_code=500)
    return OidcConfig(
        issuer=issuer,
        client_id=_require("OIDC_CLIENT_ID"),
        client_secret=_require("OIDC_CLIENT_SECRET"),
        redirect_uri=_require("OIDC_REDIRECT_URI"),
        name=(os.getenv("OIDC_NAME") or "SSO").strip(),
        groups_claim=(os.getenv("OIDC_GROUPS_CLAIM") or "groups").strip(),
        role_map=_role_map(os.getenv("OIDC_ROLE_MAP") or ""),
        link_by_email=_flag("OIDC_LINK_BY_EMAIL", False),
        connect=(os.getenv("OIDC_CONNECT") or "").strip(),
        cacert=(os.getenv("OIDC_CACERT") or "").strip(),
    )
