from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel

from .env import ensure_env
from .step import Step
from .steps import SETUP_STEPS


def run(steps: Sequence[Step], done: str) -> None:
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
    console.print(f"[green]{done}[/] Restart the API process if it is running.")


def main() -> None:
    try:
        run(SETUP_STEPS, "Setup complete.")
    except KeyboardInterrupt:
        raise SystemExit(130) from None
