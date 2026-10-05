from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt
from rich.table import Table

from settings import DEFAULT_CHAT_QUESTIONS, DEFAULT_LLM_PARALLEL, MAX_LLM_PARALLEL

from ..env import ENV_PATH, env_value, upsert_env
from .llm import BY_TAG

_GIB = 1024**3
_MAX_QUESTIONS = 1000
# Unknown model: assume a mid-sized one.
_UNKNOWN_KV_BYTES_PER_TOKEN = 100_000

NOTES = """\
[bold]Questions per 10 minutes[/] is a limit per user. Every question counts, \
answered or stopped. Past it the user sees when they can ask again. \
0 = no limit. In any case a user gets one answer at a time: a second question \
(another tab, another window) waits until the first answer is finished or \
stopped.

[bold]Simultaneous answers[/] is how many questions the LLM answers at once; \
the rest wait in line. The model is loaded once, but every simultaneous answer \
reserves its own context memory (table below; RAM, or GPU memory with a GPU). \
The answers share the processor, so each is written somewhat slower while the \
total is higher. With a GPU, 4-8 works well; on a CPU-only server more than 2 \
gains little."""


def _int_env(key: str, default: int) -> int:
    try:
        return int(env_value(ENV_PATH, key) or default)
    except ValueError:
        return default


def _ask(console: Console, label: str, default: int, low: int, high: int) -> int:
    while True:
        value = IntPrompt.ask(label, default=default, console=console)
        if low <= value <= high:
            return value
        console.print(f"Enter a number from {low} to {high}.")


class ChatStep:
    title = "Chat capacity"

    def run(self, console: Console) -> None:
        console.print(Panel(NOTES, title="Sharing the assistant", expand=False))
        model = env_value(ENV_PATH, "LLM_MODEL") or ""
        context = _int_env("LLM_NUM_CTX", 16384)
        option = BY_TAG.get(model)
        per_answer = context * (option.kv_bytes_per_token if option else _UNKNOWN_KV_BYTES_PER_TOKEN)

        questions = _ask(
            console,
            "Questions per user per 10 minutes (0 = no limit)",
            _int_env("CHAT_QUESTIONS_PER_10_MIN", DEFAULT_CHAT_QUESTIONS),
            0,
            _MAX_QUESTIONS,
        )

        table = Table(title=f"Extra memory for {model or 'the LLM'}, {context} tokens of context")
        table.add_column("Simultaneous answers", justify="right")
        table.add_column("Context memory" + ("" if option else " (rough: unknown model)"))
        for count in (1, 2, 4, 8):
            table.add_row(str(count), f"up to {per_answer * count / _GIB:.1f} GB")
        console.print(table)
        parallel = _ask(
            console,
            f"Simultaneous answers (1-{MAX_LLM_PARALLEL})",
            _int_env("LLM_PARALLEL", DEFAULT_LLM_PARALLEL),
            1,
            MAX_LLM_PARALLEL,
        )

        upsert_env(ENV_PATH, "CHAT_QUESTIONS_PER_10_MIN", str(questions))
        upsert_env(ENV_PATH, "LLM_PARALLEL", str(parallel))
        console.print(
            f"Wrote CHAT_QUESTIONS_PER_10_MIN={questions} and LLM_PARALLEL={parallel} to {ENV_PATH}"
        )
