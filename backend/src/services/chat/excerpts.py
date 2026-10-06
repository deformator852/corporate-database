"""Long documents in the prompt. A document longer than its share of the LLM
context is replaced by excerpts around the search hits, so a clause deep in
a long contract still reaches the model; a cut from the start would drop it.
"""

from dataclasses import replace

from services.chat.context_document import ContextDocument
from services.search.rag import Rag, SearchHit

# Chunks taken on each side of a search hit.
EXCERPT_RADIUS = 3
_EXCERPT_NOTE = "[Excerpts from a longer document]\n"


async def fit_to_context(
    documents: list[ContextDocument], hits: list[SearchHit], rag: Rag, budget: int
) -> list[ContextDocument]:
    """`documents` as the LLM sees them, each within `budget` characters
    where its hits allow; without hits a document keeps its start."""
    fitted: list[ContextDocument] = []
    for document in documents:
        hit_indexes = [hit.chunk_index for hit in hits if hit.document_id == document.document_id]
        if len(document.text) <= budget or not hit_indexes:
            fitted.append(document)
            continue
        wanted = sorted(
            {
                index + offset
                for index in hit_indexes
                for offset in range(-EXCERPT_RADIUS, EXCERPT_RADIUS + 1)
                if index + offset >= 0
            }
        )
        excerpt = build_excerpt(await rag.chunks_by_index(document.document_id, wanted), hit_indexes, budget)
        fitted.append(replace(document, text=_EXCERPT_NOTE + excerpt) if excerpt else document)
    return fitted


def build_excerpt(chunks: dict[int, tuple[str, int]], hits: list[int], budget: int) -> str:
    """Hit chunks first, then their neighbours at distance 1, 2, ... while
    they fit `budget` characters; joined in document order without repeating
    the overlap between neighbours. Gaps are marked with "…"."""
    order: list[int] = list(dict.fromkeys(hits))
    for distance in range(1, EXCERPT_RADIUS + 1):
        for hit in dict.fromkeys(hits):
            order += [hit - distance, hit + distance]
    selected: set[int] = set()
    used = 0
    for index in order:
        entry = chunks.get(index)
        if entry is None or index in selected or used + len(entry[0]) > budget:
            continue
        selected.add(index)
        used += len(entry[0])
    parts: list[str] = []
    previous: int | None = None
    for index in sorted(selected):
        text, start = chunks[index]
        if previous is not None and index == previous + 1:
            parts[-1] += _continuation(chunks[previous], (text, start))
        else:
            parts.append(text)
        previous = index
    return "\n…\n".join(part.strip() for part in parts)


def _continuation(before: tuple[str, int], after: tuple[str, int]) -> str:
    """`after` without the text it repeats from `before`, cut exactly by the
    chunks' start offsets in the document."""
    (before_text, before_start), (after_text, after_start) = before, after
    shared = before_start + len(before_text) - after_start
    if shared > 0:
        return after_text[shared:]
    # Not adjacent in the text (whitespace between chunks).
    return "\n" + after_text
