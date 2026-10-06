"""Checks the sources the chat model names, on the questions of the dataset.

    cd backend && uv run python evals/chat_sources.py [LANGUAGE]

Uses EMBEDDING_MODEL, its min_score, LLM_MODEL and Ollama from .env, so it
measures this installation. For each question it passes the documents the chat
would pass (the two best above min_score) to the real generator and checks:

* answered questions: the documents named as sources hold the answer,
* questions without an answer: no sources are named,
* the SOURCES line never shows in the streamed text.
"""

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from search_relevance import kept, score  # noqa: E402

from schemas.chat import ChatMessageSchema
from services.chat.context_document import ContextDocument
from services.chat.generator import OllamaGenerator  # noqa: E402
from settings import embedding_model, language  # noqa: E402


async def main(lang: str) -> None:
    from sentence_transformers import SentenceTransformer

    spec = embedding_model()
    data = json.loads(Path(__file__).with_name(f"dataset.{lang}.json").read_text())
    scores = score(SentenceTransformer(spec.hf_id), spec, lang)
    generator = OllamaGenerator()
    right = wrong_sources = leaked = 0
    for item, (expected, best) in zip(data["questions"], scores, strict=True):
        given = sorted(kept(best, spec.min_score or 0.0), key=lambda doc: -best[doc])
        documents = [
            ContextDocument(index, doc, f"{doc}.txt", "standard", data["documents"][doc])
            for index, doc in enumerate(given)
        ]
        streamed: list[str] = []

        async def collect(piece: str, out: list[str] = streamed) -> None:
            out.append(piece)

        answer, used = await generator.complete([ChatMessageSchema(role="user", content=item["q"])], documents, collect)
        named = {d.name for d in used}
        ok = named == expected if expected else not named
        right += ok
        wrong_sources += bool(named - expected)
        leaked += "sources:" in "".join(streamed).lower()
        print(f"{'ok' if ok else 'XX'} given={given} named={sorted(named)} expected={sorted(expected)} | {item['q']}")
        if not ok:
            print(f"     answer: {answer[:140]!r}")
    total = len(data["questions"])
    print(
        f"\nRight sources {right}/{total}; answers naming a wrong document {wrong_sources}; "
        f"sources line leaked {leaked}"
    )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else language()))
