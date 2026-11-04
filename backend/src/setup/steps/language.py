from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from settings import DEFAULT_LANGUAGE, LANGUAGES

from ..env import ENV_PATH, env_value, upsert_env
from ..prompts import ask_int


def current_language() -> str:
    value = env_value(ENV_PATH, "APP_LANGUAGE")
    return value if value in LANGUAGES else DEFAULT_LANGUAGE


def current_languages() -> list[str]:
    """APP_LANGUAGES, the default language first; one language when unset."""
    default = current_language()
    codes = [code.strip() for code in (env_value(ENV_PATH, "APP_LANGUAGES") or "").split(",")]
    return list(dict.fromkeys([default, *(code for code in codes if code in LANGUAGES)]))


def _table(console: Console, codes: list[str], chosen: list[str]) -> None:
    table = Table(title="Languages")
    table.add_column("#", justify="right")
    table.add_column("Language")
    for index, code in enumerate(codes, start=1):
        table.add_row(
            str(index),
            LANGUAGES[code] + ("  (current)" if code in chosen else ""),
            style="green" if code in chosen else None,
        )
    console.print(table)


def _pick_one(console: Console, codes: list[str], default: str, prompt: str) -> str:
    return codes[ask_int(console, prompt, codes.index(default) + 1, 1, len(codes)) - 1]


def _pick_several(console: Console, codes: list[str], current: list[str]) -> list[str]:
    default = ",".join(str(codes.index(code) + 1) for code in current) if len(current) > 1 else ""
    while True:
        raw = Prompt.ask(
            "Languages (numbers separated by commas, for example 1,2)", default=default or None, console=console
        )
        try:
            numbers = [int(part) for part in (raw or "").split(",") if part.strip()]
        except ValueError:
            numbers = []
        if numbers and all(1 <= number <= len(codes) for number in numbers):
            chosen = list(dict.fromkeys(codes[number - 1] for number in numbers))
            if len(chosen) > 1:
                return chosen
        console.print(f"Enter at least two numbers from 1 to {len(codes)}, for example 1,2.")


class LanguageStep:
    title = "System language"

    def current(self) -> str | None:
        if env_value(ENV_PATH, "APP_LANGUAGE") is None:
            return None
        codes = current_languages()
        if len(codes) == 1:
            return LANGUAGES[codes[0]]
        return ", ".join([f"{LANGUAGES[codes[0]]} (default)", *(LANGUAGES[code] for code in codes[1:])])

    def run(self, console: Console) -> None:
        console.print(
            "Archfold works in one language or in several. With several, each user picks their language "
            "with a button at the top of the page, and the assistant answers in it. The search models "
            "offered next are the ones that read every chosen language."
        )
        current = current_languages()
        codes = list(LANGUAGES)
        _table(console, codes, current)
        multilingual = Confirm.ask(
            "Use more than one language?",
            default=len(current) > 1,
            console=console,
        )
        if multilingual:
            chosen = _pick_several(console, codes, current)
            default = current[0] if current[0] in chosen else chosen[0]
            default = _pick_one(
                console,
                chosen,
                default,
                "Language for users who have not picked one ("
                + ", ".join(f"{index} {LANGUAGES[code]}" for index, code in enumerate(chosen, start=1))
                + ")",
            )
        else:
            default = _pick_one(console, codes, current[0], "Language (number)")
            chosen = [default]
        enabled = ",".join([default, *(code for code in chosen if code != default)])
        upsert_env(ENV_PATH, "APP_LANGUAGE", default)
        upsert_env(ENV_PATH, "APP_LANGUAGES", enabled)
        console.print(f"Wrote APP_LANGUAGE={default} and APP_LANGUAGES={enabled} to {ENV_PATH}")
