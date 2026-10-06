"""What gets embedded for each chunk: the chunk cleaned by rules (page
furniture and lines many documents share left out) and, for tables, the
header row. A table is cut into chunks, and a chunk deep in it
alone ("E1052,Greta Weber,Legal,Lyon,2052") does not say which column is the
phone extension. Only the vectors see this; the Qdrant payload keeps the
chunk as written.

Measured with evals/chunk_context.py: the header row never hurt search and
often helped. Prefixing the document name and section path was measured too
and dropped: it hurt search more often than it helped.
"""

from services.documents.text_cleanup import basic_clean, furniture_of

# Data, not prose: no line-dropping rules, which could only lose values there.
STRUCTURED = frozenset({".csv", ".json", ".xml", ".xlsx"})
# One record per line under a header row.
_TABULAR = frozenset({".csv", ".xlsx"})


def embedding_texts(
    text: str,
    chunks: list[str],
    starts: list[int],
    suffix: str,
    *,
    clean: bool,
    boilerplate: frozenset[str] = frozenset(),
) -> list[str]:
    """`boilerplate`: lines many documents share (boilerplate.py), left out
    like page furniture."""
    structured = suffix in STRUCTURED
    page_furniture = furniture_of(text) if clean and not structured else None

    def furniture(line: str) -> bool:
        return bool(page_furniture and page_furniture(line)) or line in boilerplate

    header = ""
    if suffix in _TABULAR:
        header = next((line.strip() for line in text.split("\n") if line.strip()), "")
    texts: list[str] = []
    for chunk, start in zip(chunks, starts, strict=True):
        body = chunk
        if clean:
            body = basic_clean(chunk, structured=structured, furniture=furniture) or chunk
        # The first chunk already starts with the header row.
        texts.append(f"{header}\n{body}" if header and start > 0 else body)
    return texts
