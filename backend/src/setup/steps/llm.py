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
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from ..env import ENV_PATH, env_value, upsert_env

_GIB = 1024**3


@dataclass(frozen=True, slots=True)
class LlmOption:
    tag: str
    summary: str
    disk_bytes: int
    ram_min: str
    ram_recommended: str


OPTIONS: tuple[LlmOption, ...] = (
    LlmOption("llama3.1:8b", "English, 8B", int(4.9 * _GIB), "8 GB", "16 GB"),
    LlmOption("llama3.2:3b", "Smaller and faster", int(2.0 * _GIB), "4 GB", "8 GB"),
    LlmOption("qwen2.5:7b", "Multilingual", int(4.7 * _GIB), "8 GB", "16 GB"),
)


def _fmt_bytes(n: int) -> str:
    return f"{n / _GIB:.1f} GB"


def _host() -> str:
    return env_value(ENV_PATH, "LLM_HOST") or "http://127.0.0.1:11434"


def _client() -> Client:
    return Client(host=_host(), timeout=None)


def _installed() -> set[str]:
    try:
        return {model.model for model in _client().list().models if model.model}
    except (RequestError, ResponseError, OSError):
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


def _choose(console: Console, installed: set[str]) -> str:
    current = env_value(ENV_PATH, "LLM_MODEL")
    free = shutil.disk_usage("/").free
    table = Table(title="LLM models")
    table.add_column("#", justify="right")
    table.add_column("Model")
    table.add_column("Disk")
    table.add_column("RAM min")
    table.add_column("RAM recommended")
    table.add_column("Downloaded")
    table.add_column("Notes")
    default = 1
    for index, option in enumerate(OPTIONS, start=1):
        if option.tag == current:
            default = index
        table.add_row(
            str(index),
            option.tag,
            _fmt_bytes(option.disk_bytes),
            option.ram_min,
            option.ram_recommended,
            "yes" if option.tag in installed else "no",
            option.summary + ("  (current)" if option.tag == current else ""),
            style="green" if option.tag == current else None,
        )
    other = len(OPTIONS) + 1
    catalog = {option.tag for option in OPTIONS}
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
    console.print(f"Free disk: {_fmt_bytes(free)}")
    if current and current not in catalog:
        default = other

    while True:
        choice = IntPrompt.ask("Choice", default=default, console=console)
        if 1 <= choice <= len(OPTIONS):
            selected = OPTIONS[choice - 1]
            if (
                selected.disk_bytes * 11 // 10 > free
                and selected.tag not in installed
            ):
                console.print(
                    f"[yellow]This model needs about "
                    f"{_fmt_bytes(selected.disk_bytes)}; "
                    f"only {_fmt_bytes(free)} is free.[/]"
                )
            return selected.tag
        if choice == other:
            tag = Prompt.ask("Ollama model tag", console=console).strip()
            if tag and not any(ch.isspace() for ch in tag):
                return tag
            console.print("Enter a single Ollama tag, for example llama3.1:8b.")
            continue
        console.print(f"Enter a number from 1 to {other}.")


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
        tag = _choose(console, _installed())
        _pull(console, tag)
        upsert_env(ENV_PATH, "LLM_MODEL", tag)
        console.print(f"Wrote LLM_MODEL={tag} to {ENV_PATH}")
