import shutil
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.constants import HF_HUB_CACHE
from qdrant_client import QdrantClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from settings import EMBEDDING_MODELS, LANGUAGES

from ..env import ENV_PATH, env_value, upsert_env
from ..prompts import GIB, ask_int, gib, warn_if_no_room
from .language import current_languages

_COLLECTION = "documents"


@dataclass(frozen=True, slots=True)
class EmbeddingOption:
    key: str
    summary: str
    disk_bytes: int
    ram_min: str
    ram_recommended: str

    @property
    def hf_id(self) -> str:
        return EMBEDDING_MODELS[self.key].hf_id

    @property
    def dims(self) -> int:
        return EMBEDDING_MODELS[self.key].dims


def _small(key: str, gib: float) -> EmbeddingOption:
    return EmbeddingOption(key, "Light", int(gib * GIB), "2 GB", "4 GB")


def _medium(key: str, gib: float) -> EmbeddingOption:
    return EmbeddingOption(key, "Balanced (default)", int(gib * GIB), "4 GB", "8 GB")


def _large(key: str, gib: float) -> EmbeddingOption:
    return EmbeddingOption(key, "Best quality", int(gib * GIB), "8 GB", "16 GB")


_E5_SMALL = _small("multilingual-e5-small", 2.1)
_E5_BASE = _medium("multilingual-e5-base", 5.0)
_BGE_M3 = _large("bge-m3", 4.3)

# APP_LANGUAGE → light, balanced, best. Disk is the full Hugging Face snapshot.
OPTIONS: dict[str, tuple[EmbeddingOption, ...]] = {
    "en": (
        _small("bge-small-en", 0.4),
        _medium("bge-base-en", 1.2),
        _large("bge-large-en", 3.7),
    ),
    "fr": (
        _E5_SMALL,
        _medium("solon-base", 1.1),
        _large("solon-large", 2.1),
    ),
    "es": (_E5_SMALL, _E5_BASE, _BGE_M3),
}
# Several APP_LANGUAGES: models that match a question with documents in any
# of them.
MULTILINGUAL = (_E5_SMALL, _E5_BASE, _BGE_M3)


def options_for(languages: list[str]) -> tuple[EmbeddingOption, ...]:
    return OPTIONS[languages[0]] if len(languages) == 1 else MULTILINGUAL


def _names(languages: list[str]) -> str:
    names = [LANGUAGES[code] for code in languages]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _cache_dir(hf_id: str) -> Path:
    return Path(HF_HUB_CACHE) / ("models--" + hf_id.replace("/", "--"))


def _cached(hf_id: str) -> bool:
    return _cache_dir(hf_id).exists()


def _rag_points() -> int | None:
    host = env_value(ENV_PATH, "QDRANT_HOST")
    raw_port = env_value(ENV_PATH, "QDRANT_PORT") or "6333"
    if not host:
        return None
    try:
        port = int(raw_port)
        client = QdrantClient(
            host=host,
            port=port,
            api_key=env_value(ENV_PATH, "QDRANT_API_KEY"),
            https=False,
            timeout=2,
        )
        if not client.collection_exists(_COLLECTION):
            return 0
        info = client.get_collection(_COLLECTION)
        return int(info.points_count or 0)
    except Exception:
        return None


def _download(console: Console, option: EmbeddingOption) -> None:
    if _cached(option.hf_id):
        console.print(f"{option.key} is already downloaded.")
        return
    console.print(f"Downloading {option.hf_id}…")
    try:
        snapshot_download(option.hf_id)
    except Exception as exc:
        console.print(f"[red]Could not download {option.key}: {exc}[/]")


def _choose(console: Console, languages: list[str]) -> EmbeddingOption:
    options = options_for(languages)
    current = env_value(ENV_PATH, "EMBEDDING_MODEL")
    free = shutil.disk_usage("/").free
    table = Table(title=f"Embedding models for {_names(languages)} documents")
    table.add_column("#", justify="right")
    table.add_column("Model")
    table.add_column("Disk")
    table.add_column("RAM min")
    table.add_column("RAM recommended")
    table.add_column("Dims")
    table.add_column("Downloaded")
    table.add_column("Notes")
    default = 2
    for index, option in enumerate(options, start=1):
        if option.key == current:
            default = index
        table.add_row(
            str(index),
            option.key,
            gib(option.disk_bytes),
            option.ram_min,
            option.ram_recommended,
            str(option.dims),
            "yes" if _cached(option.hf_id) else "no",
            option.summary + ("  (current)" if option.key == current else ""),
        )
    console.print(table)
    if len(languages) == 1:
        console.print(
            f"[yellow]These models are tuned for {_names(languages)}: documents in "
            "other languages are found less reliably.[/]"
        )
    else:
        console.print("These models find documents in any of the chosen languages, whatever the question's language.")
    console.print(f"Free disk: {gib(free)}")
    selected = options[ask_int(console, "Choice", default, 1, len(options)) - 1]
    if not _cached(selected.hf_id):
        warn_if_no_room(console, selected.disk_bytes, free)
    return selected


def _lock(console: Console, message: str, current: str | None) -> None:
    console.print(Panel(message, title="Locked", style="yellow"))
    if current:
        console.print(f"Keeping EMBEDDING_MODEL={current}.")


class EmbeddingStep:
    title = "Embedding model"

    def run(self, console: Console) -> None:
        points = _rag_points()
        current = env_value(ENV_PATH, "EMBEDDING_MODEL")
        if points is None:
            _lock(
                console,
                "Qdrant is not reachable. Start Docker with the project "
                "compose stack before choosing an embedding model.",
                current,
            )
            return
        languages = current_languages()
        if current and len(languages) > 1 and current not in {option.key for option in MULTILINGUAL}:
            console.print(
                f"[yellow]{current} is tuned for one language. For {_names(languages)} documents, switch to a "
                "multilingual model: uv run switch-embedding-model multilingual-e5-base[/]"
            )
        if points:
            _lock(
                console,
                "The embedding model cannot be changed here while Qdrant "
                f"collection '{_COLLECTION}' has {points} point(s): every "
                "document must be embedded again. Use uv run switch-embedding-model MODEL.",
                current,
            )
            return

        console.print(
            Panel(
                "If the selected model is not already downloaded, it will be "
                "pulled from Hugging Face now. That can take several minutes "
                "and uses the disk space in the table.",
                title="Warning",
                style="yellow",
            )
        )
        console.print("A larger embedding model usually finds more relevant documents. It needs more disk and RAM.")
        selected = _choose(console, languages)
        upsert_env(ENV_PATH, "EMBEDDING_MODEL", selected.key)
        console.print(f"Wrote EMBEDDING_MODEL={selected.key} to {ENV_PATH}")
        _download(console, selected)
