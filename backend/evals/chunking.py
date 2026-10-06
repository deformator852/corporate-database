"""Measures cutting documents at their sections (processor._split_text)
against cutting by size alone, as before.

    cd backend && uv run python evals/chunking.py [MODEL]

Default: EMBEDDING_MODEL from .env; chunk size and overlap from .env too.
English only: the sectioned documents of dataset_long.en.json and the tables
of evals/chunk_context.py, with the short documents of dataset.en.json
competing. Both ways embed what the worker embeds (embedding_text.py).
Scores as evals/search_relevance.py does.

2026-10-05, right document first, by size / sections, chunks of 400 and
800: bge-base-en 93/96 and 71/82 %, multilingual-e5-base 89/93 and 82/86 %,
bge-m3 93/93 and 86/86 %. The gap to the wrong documents grew everywhere;
needed documents kept fell once (e5 at 800: 93 -> 89 %).
"""

import json
import os
import random
import sys
from pathlib import Path

from chonkie import RecursiveChunker
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from chunk_context import tables  # noqa: E402
from text_cleanup import evaluate  # noqa: E402

from services.documents.embedding_text import embedding_texts  # noqa: E402
from services.documents.processor import _split_span, _split_text  # noqa: E402
from settings import EMBEDDING_MODELS, chunk_overlap, chunk_size  # noqa: E402


def main(model_key: str) -> None:
    from sentence_transformers import SentenceTransformer

    spec = EMBEDDING_MODELS[model_key]
    model = SentenceTransformer(spec.hf_id)
    folder = Path(__file__).parent
    long = json.loads((folder / "dataset_long.en.json").read_text())
    short = json.loads((folder / "dataset.en.json").read_text())
    generated, table_questions = tables(random.Random(11))
    documents = {
        **{name: (text, ".md") for name, text in long["documents"].items()},
        **{name: (text, ".csv") for name, text in generated.items()},
        **{key.capitalize(): (text, ".txt") for key, text in short["documents"].items()},
    }
    questions = long["questions"] + table_questions
    chunker = RecursiveChunker(tokenizer="character", chunk_size=chunk_size())
    ways = {
        "by size": lambda text: _split_span(chunker, text, chunk_overlap(), 0, len(text)),
        "sections": lambda text: _split_text(chunker, text, chunk_overlap()),
    }
    print(
        f"{model_key}: chunks of {chunk_size()}/{chunk_overlap()}, {len(questions)} questions, "
        f"min_score {spec.min_score}"
    )
    print(
        f"{'':9} {'chunks':>6} {'right first':>11} {'MRR':>6} {'margin':>7} "
        f"{'needed kept':>12} {'no-answer misled':>17}"
    )
    for label, split in ways.items():
        texts = {}
        for name, (text, suffix) in documents.items():
            chunks, starts = split(text)
            texts[name] = embedding_texts(text, chunks, starts, suffix, clean=True)
        m = evaluate(model, spec, questions, texts)
        count = sum(len(chunks) for chunks in texts.values())
        print(
            f"{label:9} {count:>6} {m['first']:>11.0%} {m['mrr']:>6.3f} {m['margin']:>7.3f} "
            f"{m['kept']:>12.0%} {m['misled']:>17.0%}"
        )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.environ["EMBEDDING_MODEL"])
