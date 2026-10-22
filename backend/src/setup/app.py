from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from .env import ENV_PATH, ensure_env, env_value, upsert_env
from .step import Step
from .steps import SETUP_STEPS


def run(steps: Sequence[Step], done: str, *, footer: str | None = None) -> None:
    console = Console()
    console.print(
        Panel(
            "Docker must be running with the project compose stack "
            "(at least Qdrant and Ollama), or this command cannot finish "
            "correctly.",
            title="Warning",
            style="yellow",
        )
    )
    ensure_env(console)
    for step in steps:
        console.rule(step.title)
        describe = getattr(step, "current", None)
        current = describe() if callable(describe) else None
        if current is not None:
            console.print(f"Now: {current}")
            if not Confirm.ask("Change it?", default=False, console=console):
                continue
        step.run(console)
    console.print(f"[green]{done}[/]")
    if footer:
        console.print(footer)


def main() -> None:
    """`uv run install`: the first installation, once. Later changes go
    through `uv run configure`."""
    console = Console()
    if env_value(ENV_PATH, "INSTALLED") == "true":
        console.print(f"Corpus is already installed ({ENV_PATH}). Change its settings with [bold]uv run configure[/].")
        raise SystemExit(1)
    try:
        run(SETUP_STEPS, "Installation complete. Change the settings later with uv run configure.")
        # Only once every step is done: stopped halfway, install runs again.
        upsert_env(ENV_PATH, "INSTALLED", "true")
    except KeyboardInterrupt:
        print()  # end the line ^C left open
        raise SystemExit(130) from None
