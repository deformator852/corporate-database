from typing import Protocol

from rich.console import Console


class Step(Protocol):
    title: str

    def run(self, console: Console) -> None: ...
