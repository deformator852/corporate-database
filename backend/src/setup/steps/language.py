from rich.console import Console
from rich.prompt import IntPrompt
from rich.table import Table

from settings import DEFAULT_LANGUAGE, LANGUAGES

from ..env import ENV_PATH, env_value, upsert_env


def current_language() -> str:
    value = env_value(ENV_PATH, "APP_LANGUAGE")
    return value if value in LANGUAGES else DEFAULT_LANGUAGE


class LanguageStep:
    title = "System language"

    def run(self, console: Console) -> None:
        console.print(
            "The interface, the assistant's answers, and the embedding models "
            "offered next all follow this language."
        )
        current = current_language()
        codes = list(LANGUAGES)
        table = Table(title="Languages")
        table.add_column("#", justify="right")
        table.add_column("Language")
        for index, code in enumerate(codes, start=1):
            table.add_row(
                str(index),
                LANGUAGES[code] + ("  (current)" if code == current else ""),
                style="green" if code == current else None,
            )
        console.print(table)
        default = codes.index(current) + 1
        while True:
            choice = IntPrompt.ask("Choice", default=default, console=console)
            if 1 <= choice <= len(codes):
                break
            console.print(f"Enter a number from 1 to {len(codes)}.")
        code = codes[choice - 1]
        upsert_env(ENV_PATH, "APP_LANGUAGE", code)
        console.print(f"Wrote APP_LANGUAGE={code} to {ENV_PATH}")
