"""Calibrates the relevance threshold of each embedding model.

    cd backend && uv run python evals/search_relevance.py [MODEL ...]

dataset.LANG.json holds company documents and questions: most have their
answer in one document, some in two, the rest in none (off-topic and
near-topic). dataset_long.LANG.json, where it exists, adds long documents
with sections, whose chunks score lower than whole short documents. For each
model and each language the setup offers it for, the script embeds
everything with the real model, scores each document by its best chunk
(cosine, as Qdrant does) and picks the `min_score` that misjudges the fewest
questions. Like the chat, it keeps at most two documents scoring at least
`min_score`.

Losing a needed document counts three times as much as giving documents to a
question that has no answer: a lost document loses the answer, while the
model still says "no relevant documents" and lists no sources for the other.
Put the result into EmbeddingSpec.min_score in settings.py. Without arguments
it calibrates every model the setup offers; the first run downloads them.
"""

import json
import statistics
import sys
from pathlib import Path

from chonkie import RecursiveChunker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.documents.embedding_text import embedding_texts  # noqa: E402
from services.documents.processor import _split_text  # noqa: E402
from settings import EMBEDDING_MODELS, chunk_overlap, chunk_size  # noqa: E402
from setup.steps.embedding import OPTIONS  # noqa: E402

LOST_WEIGHT = 3
MAX_DOCS = 2  # services/chat/chat.py _MAX_DOCS
Scores = list[tuple[set[str], dict[str, float]]]


def languages_of(model_key: str) -> list[str]:
    return [lang for lang, options in OPTIONS.items() if model_key in {o.key for o in options}]


def score(model, spec, language: str) -> Scores:
    """(expected document, best score per document) for every question."""
    return score_file(model, spec, Path(__file__).with_name(f"dataset.{language}.json"))


def score_file(model, spec, path: Path) -> Scores:
    data = json.loads(path.read_text())
    chunker = RecursiveChunker(tokenizer="character", chunk_size=chunk_size())
    owners: list[str] = []
    passages: list[str] = []
    for name, text in data["documents"].items():
        # Embedded as the worker embeds it: cut at sections, cleaned.
        chunks, starts = _split_text(chunker, text, chunk_overlap())
        owners += [name] * len(chunks)
        passages += [spec.passage_prefix + t for t in embedding_texts(text, chunks, starts, ".md", clean=True)]
    chunk_vectors = model.encode(passages, normalize_embeddings=True)
    questions = data["questions"]
    query_vectors = model.encode([spec.query_prefix + q["q"] for q in questions], normalize_embeddings=True)
    result: Scores = []
    for item, query in zip(questions, query_vectors, strict=True):
        best: dict[str, float] = {}
        for owner, value in zip(owners, (chunk_vectors @ query).tolist(), strict=True):
            best[owner] = max(best.get(owner, -1.0), value)
        expected = item["doc"] or []
        result.append((set([expected] if isinstance(expected, str) else expected), best))
    return result


def kept(best: dict[str, float], min_score: float) -> set[str]:
    """What the chat passes to the model: the two best documents above the threshold."""
    ranked = sorted(best.items(), key=lambda pair: pair[1], reverse=True)[:MAX_DOCS]
    return {doc for doc, value in ranked if value >= min_score}


def errors(scores: Scores, min_score: float) -> tuple[int, int]:
    """(needed documents lost, questions without an answer given documents)."""
    lost = misled = 0
    for expected, best in scores:
        chosen = kept(best, min_score)
        lost += len(expected - chosen)
        misled += int(not expected and bool(chosen))
    return lost, misled


def calibrate(scores: Scores) -> tuple[float, int, int]:
    best: tuple[int, float, int, int] | None = None
    for step in range(0, 1001, 5):
        floor = step / 1000
        lost, misled = errors(scores, floor)
        cost = LOST_WEIGHT * lost + misled
        # A tie keeps the lower threshold: fewer lost answers on unseen data.
        if best is None or cost < best[0]:
            best = (cost, floor, lost, misled)
    _, floor, lost, misled = best
    return floor, lost, misled


def main() -> None:
    from sentence_transformers import SentenceTransformer

    models = sys.argv[1:] or [o.key for options in OPTIONS.values() for o in options]
    for model_key in dict.fromkeys(models):
        spec = EMBEDDING_MODELS[model_key]
        model = SentenceTransformer(spec.hf_id)
        scores: Scores = []
        for language in languages_of(model_key) or ["en"]:
            scores += score(model, spec, language)
            # Long documents with sections, where chunks score lower.
            long = Path(__file__).with_name(f"dataset_long.{language}.json")
            if long.exists():
                scores += score_file(model, spec, long)
        answered = [best[doc] for expected, best in scores for doc in expected]
        unanswered = [max(best.values()) for expected, best in scores if not expected]
        first = sum(1 for expected, best in scores if expected and max(best, key=lambda doc: best[doc]) in expected)
        floor, lost, misled = calibrate(scores)
        both = [expected <= kept(best, floor) for expected, best in scores if len(expected) > 1]
        print(
            f"{model_key:<22} languages {','.join(languages_of(model_key)) or 'en'}: "
            f"right doc first {first}/{sum(1 for expected, _ in scores if expected)}, "
            f"answer score median {statistics.median(answered):.3f}, "
            f"no-answer top median {statistics.median(unanswered):.3f}\n"
            f"{'':<22} min_score={floor:.3f} -> needed documents lost {lost}/{len(answered)}, "
            f"two-document answers complete {sum(both)}/{len(both)}, "
            f"no-answer questions given documents {misled}/{len(unanswered)}"
        )


if __name__ == "__main__":
    main()
