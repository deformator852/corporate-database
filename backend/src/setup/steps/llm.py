import shutil
from dataclasses import dataclass

from ollama import Client, RequestError, ResponseError
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Prompt
from rich.table import Table

from settings import LANGUAGES

from ..env import ENV_PATH, env_value, upsert_env
from ..prompts import GIB, ask_int, gib, warn_if_no_room
from .language import current_languages


@dataclass(frozen=True, slots=True)
class LlmOption:
    tag: str
    summary: str
    disk_bytes: int
    ram_min: str
    ram_recommended: str
    # Context memory per token of one answer (8-bit KV cache: layers x KV
    # heads x head size x 2 x ~1.06 bytes). Upper bound: models with sliding
    # window attention (Gemma) need less.
    kv_bytes_per_token: int


_LLAMA = LlmOption("llama3.1:8b", "8B, strong in EN/ES/FR", int(4.9 * GIB), "8 GB", "16 GB", 69_632)
_GEMMA_4B = LlmOption("gemma3:4b", "4B, light, 140+ languages", int(3.3 * GIB), "6 GB", "8 GB", 73_984)
_GEMMA_12B = LlmOption("gemma3:12b", "12B, best quality, 140+ languages", int(8.1 * GIB), "12 GB", "16 GB", 208_896)
_QWEN = LlmOption("qwen3:8b", "8B, 119 languages", int(5.2 * GIB), "8 GB", "16 GB", 78_336)

# APP_LANGUAGE → models that answer well in that language.
OPTIONS: dict[str, tuple[LlmOption, ...]] = {
    "en": (_LLAMA, _GEMMA_12B, _QWEN),
    "es": (_LLAMA, _GEMMA_12B, _QWEN),
    "fr": (_LLAMA, _GEMMA_12B, _QWEN),
}


def options_for(languages: list[str]) -> tuple[LlmOption, ...]:
    """Models that answer well in every one of `languages`."""
    return tuple(option for option in OPTIONS[languages[0]] if all(option in OPTIONS[code] for code in languages))


BY_TAG = {option.tag: option for option in (_LLAMA, _GEMMA_4B, _GEMMA_12B, _QWEN)}


def _host() -> str:
    return env_value(ENV_PATH, "LLM_HOST") or "http://127.0.0.1:11434"


def _client() -> Client:
    return Client(host=_host(), timeout=None)


def _installed() -> set[str]:
    try:
        return {model.model for model in _client().list().models if model.model}
    except RequestError, ResponseError, OSError:
        return set()


def _pull(console: Console, tag: str) -> None:
    installed = _installed()
    if tag in installed:
        console.print(f"{tag} is already downloaded.")
        return
    console.print(f"Downloading {tag} from Ollama…")
    try:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(tag, total=None)
            for chunk in _client().pull(tag, stream=True):
                if chunk.status:
                    progress.update(task, description=chunk.status)
                if chunk.total:
                    progress.update(
                        task,
                        total=chunk.total,
                        completed=chunk.completed or 0,
                    )
    except (RequestError, ResponseError, OSError) as exc:
        console.print(f"[red]Could not download {tag}: {exc}[/]")
        console.print(f"Pull it later: ollama pull {tag}")


def _choose(console: Console, installed: set[str], languages: list[str]) -> str:
    options = options_for(languages)
    current = env_value(ENV_PATH, "LLM_MODEL")
    free = shutil.disk_usage("/").free
    table = Table(title="LLM models for " + ", ".join(LANGUAGES[code] for code in languages))
    table.add_column("#", justify="right")
    table.add_column("Model")
    table.add_column("Disk")
    table.add_column("RAM min")
    table.add_column("RAM recommended")
    table.add_column("Downloaded")
    table.add_column("Notes")
    default = 1
    for index, option in enumerate(options, start=1):
        if option.tag == current:
            default = index
        table.add_row(
            str(index),
            option.tag,
            gib(option.disk_bytes),
            option.ram_min,
            option.ram_recommended,
            "yes" if option.tag in installed else "no",
            option.summary + ("  (current)" if option.tag == current else ""),
            style="green" if option.tag == current else None,
        )
    other = len(options) + 1
    catalog = {option.tag for option in options}
    table.add_row(
        str(other),
        "Other",
        "—",
        "—",
        "—",
        "—",
        "Custom Ollama tag",
        style="green" if current and current not in catalog else None,
    )
    console.print(table)
    if current:
        console.print(f"Current LLM: [bold]{current}[/]")
    console.print(f"Free disk: {gib(free)}")
    if current and current not in catalog:
        default = other

    choice = ask_int(console, "Choice", default, 1, other)
    if choice < other:
        selected = options[choice - 1]
        if selected.tag not in installed:
            warn_if_no_room(console, selected.disk_bytes, free)
        return selected.tag
    while True:
        tag = Prompt.ask("Ollama model tag", console=console).strip()
        if tag and not any(ch.isspace() for ch in tag):
            return tag
        console.print("Enter a single Ollama tag, for example llama3.1:8b.")


class LlmStep:
    title = "LLM model"

    def run(self, console: Console) -> None:
        console.print(
            Panel(
                "If the selected model is not already downloaded, it will be "
                "pulled from Ollama now. That can take several minutes and "
                "uses the disk space in the table.",
                title="Warning",
                style="yellow",
            )
        )
        console.print(
            "A larger LLM usually gives better answers from the documents "
            "that search already found. It does not change retrieval ranking."
        )
        tag = _choose(console, _installed(), current_languages())
        _pull(console, tag)
        upsert_env(ENV_PATH, "LLM_MODEL", tag)
        console.print(f"Wrote LLM_MODEL={tag} to {ENV_PATH}")
