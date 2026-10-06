"""Measures keyword search next to vector search (services/search/keywords.py) on
questions about one record: a code or a name deep in a table.

    cd backend && uv run python evals/keyword_search.py [MODEL]

Default: EMBEDDING_MODEL, chunk size and overlap from .env. The documents of
dataset_long.en.json, dataset.en.json and the tables of chunk_context.py go
into an in-memory Qdrant through the real Rag, as the worker indexes them.
For each table question the script checks whether the chunk holding the
record is among the hits the chat keeps (min_score, or `exact`), searching
by vector only and with keywords; long-document questions check that the
right document is still kept, and questions with no answer how often they
still get documents.

2026-10-06, chunks of 400, the record's chunk ranked first, vector only /
with keywords: bge-base-en 2/9 -> 9/9, multilingual-e5-base 4/9 -> 9/9,
bge-m3 2/9 -> 9/9. Long-document answers kept 19/19 and no-answer questions
given documents unchanged either way.
"""

import asyncio
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
from qdrant_client import AsyncQdrantClient  # noqa: E402

from services.chat.chat import _rank, _relevant  # noqa: E402
from services.documents.embedding_text import embedding_texts  # noqa: E402
from services.documents.processor import _split_text  # noqa: E402
from services.search.rag import Rag, SearchHit  # noqa: E402
from settings import EMBEDDING_MODELS, chunk_overlap, chunk_size  # noqa: E402


async def main(model_key: str) -> None:
    from sentence_transformers import SentenceTransformer

    os.environ["EMBEDDING_MODEL"] = model_key
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
    rag = Rag(AsyncQdrantClient(location=":memory:"))
    chunker = RecursiveChunker(tokenizer="character", chunk_size=chunk_size())
    ids = {}
    for document_id, (name, (text, suffix)) in enumerate(documents.items(), start=1):
        ids[document_id] = name
        chunks, starts = _split_text(chunker, text, chunk_overlap())
        indexed = embedding_texts(text, chunks, starts, suffix, clean=True)
        vectors = model.encode([spec.passage_prefix + t for t in indexed], normalize_embeddings=True).tolist()
        await rag.upsert_chunks(
            document_id=document_id,
            name=name,
            filename=name,
            classification="standard",
            chunks=chunks,
            vectors=vectors,
            starts=starts,
            indexed=indexed,
        )

    async def kept(question: str, keywords: bool) -> list[SearchHit]:
        vector = model.encode([spec.query_prefix + question], normalize_embeddings=True)[0].tolist()
        hits = await rag.search(
            vector, question=question if keywords else "", allowed_classifications=["standard"], limit=8
        )
        return _relevant(sorted(hits, key=_rank))

    print(f"{model_key}: chunks of {chunk_size()}/{chunk_overlap()}, min_score {spec.min_score}")
    for label, keywords in (("vector only", False), ("with keywords", True)):
        record_found = record_first = 0
        for item in table_questions:
            hits = await kept(item["q"], keywords)
            holding = [i for i, hit in enumerate(hits) if item["record"] in hit.text]
            record_found += bool(holding)
            record_first += holding[:1] == [0]
        doc_kept = 0
        answered = [q for q in long["questions"] if q["doc"]]
        for item in answered:
            hits = await kept(item["q"], keywords)
            doc_kept += item["doc"] in {ids[hit.document_id] for hit in hits}
        unanswered = [q for q in long["questions"] if not q["doc"]]
        misled = sum([bool(await kept(item["q"], keywords)) for item in unanswered])
        print(
            f"  {label:14} table records found {record_found}/{len(table_questions)}, "
            f"first {record_first}/{len(table_questions)}; long-document answers kept {doc_kept}/{len(answered)}; "
            f"no-answer questions given documents {misled}/{len(unanswered)}"
        )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else os.environ["EMBEDDING_MODEL"]))
