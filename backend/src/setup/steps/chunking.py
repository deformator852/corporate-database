import math
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt
from rich.table import Table

from settings import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    EMBEDDING_MODELS,
    LANGUAGES,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    EmbeddingSpec,
)

from ..env import ENV_PATH, env_value, upsert_env

# Rough page of a text document, for the disk estimate.
_CHARS_PER_PAGE = 2_500
_PAGES = 100
# Stored per chunk besides the vector: the chunk text (UTF-8, ~2 bytes per
# Cyrillic letter) and payload fields.
_PAYLOAD_OVERHEAD_BYTES = 300


@dataclass(frozen=True, slots=True)
class ChunkPreset:
    name: str
    size: int
    overlap: int
    best_for: str
    trade_off: str


PRESETS: tuple[ChunkPreset, ...] = (
    ChunkPreset(
        "Precise",
        400,
        80,
        'Exact facts: amounts, dates, one clause ("what is the amount in 3.2")',
        "About 2x the chunks of Balanced: more disk and RAM in Qdrant, "
        "longer upload and LLM cleanup. One chunk can lose its context "
        "(a clause without its heading). Search speed barely changes.",
    ),
    ChunkPreset(
        "Balanced",
        DEFAULT_CHUNK_SIZE,
        DEFAULT_CHUNK_OVERLAP,
        "Most company documents: both fact and topic questions",
        "A compromise: a small fact is diluted a little in a longer chunk.",
    ),
    ChunkPreset(
        "Broad",
        1200,
        200,
        'Topic questions: "what is this document about", long prose, policies',
        "Specific numbers and clauses rank lower. Fewer chunks, less disk. "
        "Can exceed the embedding model's input limit (see below).",
    ),
)

NOTES = """\
[bold]Chunk size[/] is how much text becomes one searchable piece. A question is \
matched against chunks, so a smaller chunk matches a specific fact more sharply \
and a larger one matches the general topic better. The assistant then answers \
from the full document text: chunk size decides how reliably the right \
document is found.

[bold]Overlap[/] repeats the end of one chunk at the start of the next, so a \
sentence cut at a boundary is still found whole. 10-20% of the chunk size is \
enough. 0 risks losing a fact split between two chunks; more than ~25% only \
adds duplicates (disk, upload time).

[bold]Search speed[/] barely changes with more chunks: Qdrant's index grows \
logarithmically. Disk and RAM grow linearly with the number of chunks.

A change applies to documents uploaded afterwards. Upload older documents \
again to re-chunk them."""

# One sentence per system language, to measure how many characters fit the
# embedding model's input.
_SAMPLES = {
    "en": "The travel request is submitted no later than seven working days before departure. ",
    "es": "La solicitud de viaje se presenta a más tardar siete días hábiles antes de la salida. ",
    "fr": "La demande de déplacement est soumise au plus tard sept jours ouvrés avant le départ. ",
}


def _current_model() -> EmbeddingSpec | None:
    return EMBEDDING_MODELS.get(env_value(ENV_PATH, "EMBEDING_MODEL") or "")


def _estimate(size: int, overlap: int, dims: int) -> tuple[int, float]:
    """Chunks and megabytes in Qdrant for 100 pages of text."""
    chunks = math.ceil(_CHARS_PER_PAGE * _PAGES / max(size - overlap, 1))
    per_chunk = dims * 4 + size * 2 + _PAYLOAD_OVERHEAD_BYTES
    return chunks, chunks * per_chunk / 1024**2


def _input_limits(spec: EmbeddingSpec) -> dict[str, int]:
    """Largest chunk (characters) per language that fits the model input;
    longer chunks are cut and their tail is not searchable. Empty when the
    tokenizer is not downloaded yet."""
    try:
        from transformers import AutoTokenizer
        from transformers.utils import logging as transformers_logging

        # Measuring deliberately feeds over-long text; its warning is noise.
        transformers_logging.set_verbosity_error()

        tokenizer = AutoTokenizer.from_pretrained(spec.hf_id, local_files_only=True)
    except Exception:
        return {}
    max_tokens = min(int(tokenizer.model_max_length), 8192)
    limits: dict[str, int] = {}
    for language, sentence in _SAMPLES.items():
        text = sentence * math.ceil(MAX_CHUNK_SIZE * 3 / len(sentence))
        low, high = 0, MAX_CHUNK_SIZE * 3
        while low < high:
            middle = (low + high + 1) // 2
            ids = tokenizer(spec.passage_prefix + text[:middle])["input_ids"]
            if len(ids) <= max_tokens:
                low = middle
            else:
                high = middle - 1
        limits[language] = low
    return limits


def _ask_custom(console: Console, size: int, overlap: int) -> tuple[int, int]:
    while True:
        size = IntPrompt.ask(
            f"Chunk size, characters ({MIN_CHUNK_SIZE}-{MAX_CHUNK_SIZE})",
            default=size,
            console=console,
        )
        if MIN_CHUNK_SIZE <= size <= MAX_CHUNK_SIZE:
            break
        console.print(f"Enter a number from {MIN_CHUNK_SIZE} to {MAX_CHUNK_SIZE}.")
    suggested = min(overlap, size // 2) if overlap else round(size * 0.18)
    while True:
        overlap = IntPrompt.ask(
            f"Overlap, characters (0-{size // 2}; 10-20% recommended)",
            default=suggested,
            console=console,
        )
        if 0 <= overlap <= size // 2:
            return size, overlap
        console.print(f"Enter a number from 0 to {size // 2}.")


class ChunkingStep:
    title = "Chunk size"

    def run(self, console: Console) -> None:
        current_size = int(env_value(ENV_PATH, "CHUNK_SIZE") or DEFAULT_CHUNK_SIZE)
        current_overlap = int(
            env_value(ENV_PATH, "CHUNK_OVERLAP") or DEFAULT_CHUNK_OVERLAP
        )
        spec = _current_model()
        dims = spec.dims if spec else 768

        console.print(Panel(NOTES, title="How chunking affects answers", expand=False))
        table = Table(title=f"Chunk presets (disk per {_PAGES} pages of text)")
        table.add_column("#", justify="right")
        table.add_column("Preset")
        table.add_column("Size / overlap")
        table.add_column("Best for")
        table.add_column("Trade-offs")
        table.add_column("Chunks")
        table.add_column("Qdrant")
        default = len(PRESETS) + 1
        for index, preset in enumerate(PRESETS, start=1):
            is_current = (preset.size, preset.overlap) == (current_size, current_overlap)
            if is_current:
                default = index
            chunks, megabytes = _estimate(preset.size, preset.overlap, dims)
            table.add_row(
                str(index),
                preset.name + ("  (current)" if is_current else ""),
                f"{preset.size} / {preset.overlap}",
                preset.best_for,
                preset.trade_off,
                f"~{chunks}",
                f"~{megabytes:.1f} MB",
                style="green" if is_current else None,
            )
        custom = len(PRESETS) + 1
        table.add_row(
            str(custom),
            "Custom" + ("  (current)" if default == custom else ""),
            f"{current_size} / {current_overlap}" if default == custom else "—",
            "Your own size and overlap",
            "—",
            "—",
            "—",
            style="green" if default == custom else None,
        )
        console.print(table)

        limits = _input_limits(spec) if spec else {}
        if limits:
            fits = ", ".join(f"{LANGUAGES[code]} ~{chars}" for code, chars in limits.items())
            console.print(
                f"Longest chunk {spec.hf_id} reads whole, in characters: {fits}. "
                "A stored chunk is size + overlap long; longer chunks are cut "
                "and their end is not searchable."
            )

        while True:
            choice = IntPrompt.ask("Choice", default=default, console=console)
            if 1 <= choice <= len(PRESETS):
                size, overlap = PRESETS[choice - 1].size, PRESETS[choice - 1].overlap
            elif choice == custom:
                size, overlap = _ask_custom(console, current_size, current_overlap)
            else:
                console.print(f"Enter a number from 1 to {custom}.")
                continue
            # The overlap is prepended, so a stored chunk is up to size + overlap.
            longest = size + overlap
            too_long = [
                LANGUAGES[code] for code, chars in limits.items() if longest > chars
            ]
            if too_long and not Confirm.ask(
                f"[yellow]Chunks of up to {longest} characters (size + overlap) "
                f"are longer than {spec.hf_id} "
                f"reads for {', '.join(too_long)} text; the end of each chunk "
                "would not be searchable. Keep this size anyway?[/]",
                default=False,
                console=console,
            ):
                continue
            break

        upsert_env(ENV_PATH, "CHUNK_SIZE", str(size))
        upsert_env(ENV_PATH, "CHUNK_OVERLAP", str(overlap))
        console.print(
            f"Wrote CHUNK_SIZE={size}, CHUNK_OVERLAP={overlap} to {ENV_PATH}. "
            "Applies to documents uploaded from now on."
        )
