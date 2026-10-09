"""Prompts and formatting the setup steps share."""

from rich.console import Console
from rich.prompt import IntPrompt

GIB = 1024**3


def gib(n: int) -> str:
    return f"{n / GIB:.1f} GB"


def ask_int(console: Console, label: str, default: int, low: int, high: int) -> int:
    """A number from `low` to `high`, asked again until it is one."""
    while True:
        value = IntPrompt.ask(label, default=default, console=console)
        if low <= value <= high:
            return value
        console.print(f"Enter a number from {low} to {high}.")


def warn_if_no_room(console: Console, needed: int, free: int) -> None:
    """A download of `needed` bytes, with a 10% margin, against `free`."""
    if needed * 11 // 10 > free:
        console.print(f"[yellow]This model needs about {gib(needed)}; only {gib(free)} is free.[/]")
