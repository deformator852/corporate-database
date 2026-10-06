"""Measures what the header row in front of embedded table chunks gives search.

    cd backend && uv run python evals/chunk_context.py [MODEL]

Default: EMBEDDING_MODEL from .env. English only: dataset_long.en.json holds
long sectioned documents whose facts do not name their topic ("Up to three
days per week are allowed" under "Remote work"); two generated tables hold
records far below their header row. The short documents of dataset.en.json
compete with them. Every document is chunked as the worker chunks it and
embedded two ways:

* plain    the chunk cleaned by rules,
* context  embedding_text.embedding_texts (what the worker embeds now).

Scores as evals/search_relevance.py does.

Also measured, 2026-10-05, then dropped: the document name and section path
("Employee handbook › Remote work") in front of every chunk. Right document
first, plain / name+section, chunks of 400 and 800 characters:
bge-base-en 93/89 and 71/75 %, multilingual-e5-base 89/86 and 82/82 %
(needed documents kept 93/82 % at 800), bge-m3 89/86 and 86/79 %.
The header row alone never scored lower and kept more needed documents:
bge-base-en 96 -> 100 % (400) and 89 -> 96 % (800), bge-m3 93 -> 100 % (400).
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

from text_cleanup import evaluate  # noqa: E402

from services.documents.embedding_text import embedding_texts  # noqa: E402
from services.documents.processor import _split_text  # noqa: E402
from services.documents.text_cleanup import basic_clean, furniture_of  # noqa: E402
from settings import EMBEDDING_MODELS, chunk_overlap, chunk_size  # noqa: E402

# Names, departments and offices for the generated tables.
FIRST = ["Anna", "Ben", "Carla", "David", "Elif", "Farid", "Greta", "Hugo", "Ines", "Jonas", "Kira", "Leon"]
LAST = ["Keller", "Novak", "Rossi", "Weber", "Yilmaz", "Dubois", "Larsen", "Costa", "Fischer", "Moreau"]
DEPARTMENTS = ["Finance", "Sales", "Legal", "Engineering", "Marketing", "Operations"]
OFFICES = ["Berlin", "Lisbon", "Warsaw", "Lyon"]


def tables(rng: random.Random) -> tuple[dict[str, str], list[dict]]:
    """Two CSV tables and questions about records deep inside them."""
    names = rng.sample([f"{f} {last}" for f in FIRST for last in LAST], 80)
    people = ["Employee ID,Name,Department,Office,Phone extension"] + [
        f"E{1000 + i},{name},{rng.choice(DEPARTMENTS)},{rng.choice(OFFICES)},{2000 + i}" for i, name in enumerate(names)
    ]
    assets = ["Asset tag,Type,Model,Assigned to,Purchase date,Warranty until"] + [
        f"LT-{3000 + i},Laptop,{rng.choice(['ThinkPad T14', 'Latitude 7440', 'EliteBook 840'])},"
        f"{names[i]},2024-{1 + i % 12:02d}-15,2027-{1 + i % 12:02d}-14"
        for i in range(60)
    ]
    questions = []
    for i in (35, 52, 71):
        questions.append(
            {"q": f"What is the phone extension of {names[i]}?", "doc": "Employee directory", "record": names[i]}
        )
        questions.append(
            {"q": f"Which office does {names[i]} work in?", "doc": "Employee directory", "record": names[i]}
        )
    for i in (30, 44, 58):
        questions.append(
            {
                "q": f"When does the warranty of laptop LT-{3000 + i} end?",
                "doc": "Hardware assets",
                "record": f"LT-{3000 + i}",
            }
        )
    return {
        "Employee directory": "\n".join(people),
        "Hardware assets": "\n".join(assets),
    }, questions


def chunked(text: str) -> tuple[list[str], list[int]]:
    chunker = RecursiveChunker(tokenizer="character", chunk_size=chunk_size())
    return _split_text(chunker, text, chunk_overlap())


def main(model_key: str) -> None:
    from sentence_transformers import SentenceTransformer

    spec = EMBEDDING_MODELS[model_key]
    model = SentenceTransformer(spec.hf_id)
    folder = Path(__file__).parent
    long = json.loads((folder / "dataset_long.en.json").read_text())
    short = json.loads((folder / "dataset.en.json").read_text())
    generated, table_questions = tables(random.Random(11))
    documents = {  # name -> (text, suffix)
        **{name: (text, ".md") for name, text in long["documents"].items()},
        **{name: (text, ".csv") for name, text in generated.items()},
        **{key.capitalize(): (text, ".txt") for key, text in short["documents"].items()},
    }
    questions = long["questions"] + table_questions
    plain: dict[str, list[str]] = {}
    context: dict[str, list[str]] = {}
    for name, (text, suffix) in documents.items():
        chunks, starts = chunked(text)
        structured = suffix == ".csv"
        furniture = furniture_of(text)
        plain[name] = [basic_clean(c, structured=structured, furniture=furniture) or c for c in chunks]
        context[name] = embedding_texts(text, chunks, starts, suffix, clean=True)
    count = sum(len(chunks) for chunks in plain.values())
    print(
        f"{model_key}: {len(questions)} questions, {len(documents)} documents, {count} chunks, "
        f"min_score {spec.min_score}"
    )
    print(f"{'':8} {'right first':>11} {'MRR':>6} {'margin':>7} {'needed kept':>12} {'no-answer misled':>17}")
    for label, texts in (("plain", plain), ("context", context)):
        m = evaluate(model, spec, questions, texts)
        print(
            f"{label:8} {m['first']:>11.0%} {m['mrr']:>6.3f} {m['margin']:>7.3f} "
            f"{m['kept']:>12.0%} {m['misled']:>17.0%}"
        )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.environ["EMBEDDING_MODEL"])
