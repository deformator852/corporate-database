from typing import Protocol

from rich.console import Console


class Step(Protocol):
    title: str

    def run(self, console: Console) -> None: ...


class Configurable(Protocol):
    """A step that can tell what it set before. Run again (configure), it is
    offered as "keep as it is", and skipped unless the operator asks."""

    def current(self) -> str | None:
        """What is set now, in a few words; None: never set, so it runs."""
        ...
