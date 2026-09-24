import shutil
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.constants import HF_HUB_CACHE
from qdrant_client import QdrantClient
from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt
from rich.table import Table

from ..env import ENV_PATH, env_value, upsert_env

_GIB = 1024**3
_COLLECTION = "documents"


@dataclass(frozen=True, slots=True)
class EmbeddingOption:
    key: str
    hf_id: str
    summary: str
    dims: int
    disk_bytes: int
    ram_min: str
    ram_recommended: str


OPTIONS: tuple[EmbeddingOption, ...] = (
    EmbeddingOption(
        "multilingual-e5-small",
        "intfloat/multilingual-e5-small",
        "Fastest, 384-d",
        384,
        int(0.47 * _GIB),
        "2 GB",
        "4 GB",
    ),
    EmbeddingOption(
        "multilingual-e5-base",
        "intfloat/multilingual-e5-base",
        "Default, 768-d",
        768,
        int(1.1 * _GIB),
        "4 GB",
        "8 GB",
    ),
    EmbeddingOption(
        "multilingual-e5-large",
        "intfloat/multilingual-e5-large",
        "Best quality, 1024-d",
        1024,
        int(2.2 * _GIB),
        "8 GB",
        "16 GB",
    ),
)


def _fmt_bytes(n: int) -> str:
    return f"{n / _GIB:.1f} GB"


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
        client = QdrantClient(host=host, port=port, timeout=2)
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


def _choose(console: Console) -> EmbeddingOption:
    current = env_value(ENV_PATH, "EMBEDING_MODEL")
    free = shutil.disk_usage("/").free
    table = Table(title="Embedding models")
    table.add_column("#", justify="right")
    table.add_column("Model")
    table.add_column("Disk")
    table.add_column("RAM min")
    table.add_column("RAM recommended")
    table.add_column("Dims")
    table.add_column("Downloaded")
    table.add_column("Notes")
    default = 2
    for index, option in enumerate(OPTIONS, start=1):
        if option.key == current:
            default = index
        table.add_row(
            str(index),
            option.key,
            _fmt_bytes(option.disk_bytes),
            option.ram_min,
            option.ram_recommended,
            str(option.dims),
            "yes" if _cached(option.hf_id) else "no",
            option.summary + ("  (current)" if option.key == current else ""),
        )
    console.print(table)
    console.print(f"Free disk: {_fmt_bytes(free)}")
    while True:
        choice = IntPrompt.ask("Choice", default=default, console=console)
        if 1 <= choice <= len(OPTIONS):
            selected = OPTIONS[choice - 1]
            if (
                selected.disk_bytes * 11 // 10 > free
                and not _cached(selected.hf_id)
            ):
                console.print(
                    f"[yellow]This model needs about "
                    f"{_fmt_bytes(selected.disk_bytes)}; "
                    f"only {_fmt_bytes(free)} is free.[/]"
                )
            return selected
        console.print(f"Enter a number from 1 to {len(OPTIONS)}.")


def _lock(console: Console, message: str, current: str | None) -> None:
    console.print(Panel(message, title="Locked", style="yellow"))
    if current:
        console.print(f"Keeping EMBEDING_MODEL={current}.")


class EmbeddingStep:
    title = "Embedding model"

    def run(self, console: Console) -> None:
        points = _rag_points()
        current = env_value(ENV_PATH, "EMBEDING_MODEL")
        if points is None:
            _lock(
                console,
                "Qdrant is not reachable. Start Docker with the project "
                "compose stack before choosing an embedding model.",
                current,
            )
            return
        if points:
            _lock(
                console,
                "The embedding model cannot be changed while Qdrant "
                f"collection '{_COLLECTION}' has {points} point(s). "
                "Delete those documents first if you need a different "
                "model.",
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
        selected = _choose(console)
        upsert_env(ENV_PATH, "EMBEDING_MODEL", selected.key)
        console.print(f"Wrote EMBEDING_MODEL={selected.key} to {ENV_PATH}")
        _download(console, selected)
