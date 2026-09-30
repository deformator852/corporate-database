import sys
from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel

from .env import ensure_env
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
        step.run(console)
    console.print(f"[green]{done}[/]")
    if footer:
        console.print(footer)


def main() -> None:
    try:
        if sys.argv[1:2] == ["key"]:
            from .key import main as key_main

            key_main(sys.argv[2:])
            return
        run(
            SETUP_STEPS,
            "Setup complete.",
            footer="Running already? Restart the backend and the worker (production: deploy/deploy.sh up).",
        )
    except KeyboardInterrupt:
        raise SystemExit(130) from None
