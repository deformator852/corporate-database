"""Measures what text cleanup gives search, on documents made noisy.

    cd backend && uv run python evals/text_cleanup.py [LANGUAGE] [MODEL]

Defaults: APP_LANGUAGE and EMBEDDING_MODEL from .env. Each document of
dataset.LANG.json gets what real files carry: a running header and page
numbers on every page, filler and introductory phrases, words broken across
lines, separator and OCR garbage lines, an e-mail signature and a
confidentiality disclaimer. The same chunks are then embedded three ways, as
the worker would embed them:

* clean    the original dataset text (the ceiling),
* noisy    noisy text, no cleanup (TEXT_CLEANUP=off),
* rules    noisy text after the rules (TEXT_CLEANUP=rules).

Scores as evals/search_relevance.py does: a document scores its best chunk,
the chat keeps the two best at or above the model's min_score.

This script also measured an LLM rewrite after the rules (llama3.1:8b),
2026-10-05. Right document first, noisy / rules / rules + LLM: en 92/92/100 %,
es 92/92/83 %, fr 71/83/83 %, at 10-24 s per chunk. No steady gain over the
rules, so the LLM step was removed.
"""

import json
import os
import random
import statistics
import sys
from pathlib import Path

from chonkie import RecursiveChunker
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from search_relevance import kept  # noqa: E402
from services.documents.processor import _split_text  # noqa: E402
from services.documents.text_cleanup import basic_clean, repeated_lines  # noqa: E402
from settings import EMBEDDING_MODELS, chunk_overlap, chunk_size, language  # noqa: E402

NOISE = {
    "en": {
        "header": "Northwind Group · Internal use only",
        "page": "Page {page} of {pages}",
        "fillers": ["It should be noted that ", "Basically, ", "As mentioned above, ", "Please note that "],
        "signature": "Best regards,\nAnna Keller\nHR Operations\nSent from my iPhone",
        "disclaimer": (
            "This message and any attachments are confidential and intended solely for the addressee. "
            "If you received it in error, notify the sender and delete it. All rights reserved."
        ),
    },
    "es": {
        "header": "Grupo Northwind · Uso interno",
        "page": "Página {page} de {pages}",
        "fillers": ["Cabe señalar que ", "Básicamente, ", "Como se mencionó anteriormente, ", "Tenga en cuenta que "],
        "signature": "Saludos cordiales,\nAnna Keller\nOperaciones de RR. HH.\nEnviado desde mi iPhone",
        "disclaimer": (
            "Este mensaje y sus anexos son confidenciales y están dirigidos únicamente a su destinatario. "
            "Si lo recibió por error, avise al remitente y elimínelo. Todos los derechos reservados."
        ),
    },
    "fr": {
        "header": "Groupe Northwind · Usage interne",
        "page": "Page {page} sur {pages}",
        "fillers": ["Il convient de noter que ", "En gros, ", "Comme mentionné ci-dessus, ", "Veuillez noter que "],
        "signature": "Cordialement,\nAnna Keller\nOpérations RH\nEnvoyé de mon iPhone",
        "disclaimer": (
            "Ce message et ses pièces jointes sont confidentiels et destinés uniquement à leur destinataire. "
            "Si vous l'avez reçu par erreur, prévenez l'expéditeur et supprimez-le. Tous droits réservés."
        ),
    },
}
GARBAGE = ["* * * * * * *", "~~ ¦ ·:· ¦¦ ~", "_______________"]
SENTENCES_PER_PAGE = 2


def noisy(text: str, lang: str, rng: random.Random) -> str:
    noise = NOISE[lang]
    sentences = [s.strip() for s in text.replace(". ", ".\n").split("\n") if s.strip()]
    pages = [sentences[i : i + SENTENCES_PER_PAGE] for i in range(0, len(sentences), SENTENCES_PER_PAGE)]
    out: list[str] = []
    for number, page in enumerate(pages, start=1):
        lines = [noise["header"]]
        for sentence in page:
            if rng.random() < 0.5:
                sentence = rng.choice(noise["fillers"]) + sentence[0].lower() + sentence[1:]
            words = sentence.split(" ")
            long = [i for i, word in enumerate(words) if len(word) >= 10 and word.isalpha()]
            if long and rng.random() < 0.5:
                i = rng.choice(long)
                words[i] = words[i][:5] + "-\n" + words[i][5:]
            lines.append(" ".join(words))
        if rng.random() < 0.5:
            lines.append(rng.choice(GARBAGE))
        lines.append(noise["page"].format(page=number, pages=len(pages)))
        out.append("\n".join(lines))
    return "\n\n".join([*out, noise["signature"], noise["disclaimer"]])


def chunks_of(text: str) -> list[str]:
    chunker = RecursiveChunker(tokenizer="character", chunk_size=chunk_size())
    return _split_text(chunker, text, chunk_overlap())[0]


def rules(text: str) -> list[str]:
    repeated = repeated_lines(text)
    return [basic_clean(chunk, repeated=repeated) or chunk for chunk in chunks_of(text)]


def evaluate(model, spec, questions: list[dict], texts: dict[str, list[str]]) -> dict[str, float]:
    owners = [name for name, chunks in texts.items() for _ in chunks]
    passages = [spec.passage_prefix + chunk for chunks in texts.values() for chunk in chunks]
    chunk_vectors = model.encode(passages, normalize_embeddings=True)
    query_vectors = model.encode([spec.query_prefix + q["q"] for q in questions], normalize_embeddings=True)
    first = lost = misled = 0
    ranks: list[float] = []
    margins: list[float] = []
    needed = 0
    for item, query in zip(questions, query_vectors, strict=True):
        best: dict[str, float] = {}
        for owner, value in zip(owners, (chunk_vectors @ query).tolist(), strict=True):
            best[owner] = max(best.get(owner, -1.0), value)
        expected = item["doc"] or []
        expected = {expected} if isinstance(expected, str) else set(expected)
        chosen = kept(best, spec.min_score or 0.0)
        if not expected:
            misled += bool(chosen)
            continue
        ranked = sorted(best, key=best.get, reverse=True)
        first += ranked[0] in expected
        ranks.append(1 / (1 + min(ranked.index(doc) for doc in expected)))
        wrong = max(value for doc, value in best.items() if doc not in expected)
        margins.append(statistics.mean(best[doc] for doc in expected) - wrong)
        needed += len(expected)
        lost += len(expected - chosen)
    answered = sum(1 for q in questions if q["doc"])
    return {
        "first": first / answered,
        "mrr": statistics.mean(ranks),
        "margin": statistics.mean(margins),
        "kept": (needed - lost) / needed,
        "misled": misled / (len(questions) - answered),
    }


def main(lang: str, model_key: str) -> None:
    from sentence_transformers import SentenceTransformer

    spec = EMBEDDING_MODELS[model_key]
    model = SentenceTransformer(spec.hf_id)
    data = json.loads(Path(__file__).with_name(f"dataset.{lang}.json").read_text())
    rng = random.Random(7)
    dirty = {name: noisy(text, lang, rng) for name, text in data["documents"].items()}
    variants = {
        "clean": {name: chunks_of(text) for name, text in data["documents"].items()},
        "noisy": {name: chunks_of(text) for name, text in dirty.items()},
        "rules": {name: rules(text) for name, text in dirty.items()},
    }
    print(f"{model_key}, {lang}: {len(data['questions'])} questions, min_score {spec.min_score}")
    print(f"{'':6} {'right first':>11} {'MRR':>6} {'margin':>7} {'needed kept':>12} {'no-answer misled':>17}")
    for name, texts in variants.items():
        m = evaluate(model, spec, data["questions"], texts)
        print(
            f"{name:6} {m['first']:>11.0%} {m['mrr']:>6.3f} {m['margin']:>7.3f} "
            f"{m['kept']:>12.0%} {m['misled']:>17.0%}"
        )


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[0] if args else language(), args[1] if len(args) > 1 else os.environ["EMBEDDING_MODEL"])
