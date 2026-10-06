"""Cleanup rules, long-document excerpts."""

from chonkie import RecursiveChunker

from services.chat.excerpts import build_excerpt
from services.documents.embedding_text import embedding_texts
from services.documents.processor import _split_text
from services.documents.text_cleanup import basic_clean, furniture_of


def test_rules_drop_page_furniture_but_keep_content():
    text = "Report\n2025\nRevenue grew by 12%.\n- 4 -\nPage 5 of 20\nACME\nx\nACME\ny\nACME\nSee sec-\ntion 3."
    cleaned = basic_clean(text)
    assert "2025" in cleaned and "12%" in cleaned and "section 3." in cleaned
    assert "- 4 -" not in cleaned and "Page 5" not in cleaned and "ACME" not in cleaned


def test_a_chunk_drops_the_headers_of_its_whole_document():
    document = "ACME internal\nBudget is 500 EUR.\nACME internal\nTrips need approval.\nACME internal\nEnd."
    chunk = "ACME internal\nBudget is 500 EUR."  # the header shows once here
    assert basic_clean(chunk, furniture=furniture_of(document)) == "Budget is 500 EUR."


def test_table_chunks_are_embedded_with_the_header_row():
    table = "Name,Extension\nAna,101\nBen,102"
    chunks, starts = ["Name,Extension\nAna,101", "Ben,102"], [0, table.index("Ben")]
    assert embedding_texts(table, chunks, starts, ".csv", clean=True) == [
        "Name,Extension\nAna,101",  # already starts with it
        "Name,Extension\nBen,102",
    ]
    assert embedding_texts("Intro\nBody", ["Body"], [6], ".txt", clean=True) == ["Body"]


def test_a_pdf_loses_lines_at_its_page_edges_only():
    topics = ["Sales grew in spring.", "Costs fell after the audit.", "Hiring slowed down.", "Rent stays flat."]
    pages = [
        f"ACME report\n{topic}\nApproved\nYes\n120\n{topic[:9]} ends.\nPage {i} of 4"
        for i, topic in enumerate(topics, 1)
    ]
    document = "\n\f\n".join(pages)
    cleaned = basic_clean(pages[1], furniture=furniture_of(document))
    # The header and "Page 2 of 4" sit at every page edge; "Yes" and "120"
    # repeat too, but inside the pages: table values, kept.
    assert cleaned == "Costs fell after the audit.\nApproved\nYes\n120\nCosts fel ends."


def test_chunks_never_cross_a_section():
    section = "Text of the section, long enough to fill most of a chunk. " * 4
    text = f"# Remote work\n{section}\n# Equipment\n{section}\n# Short\nA.\n# Shorter\nB."
    chunks, starts = _split_text(RecursiveChunker(tokenizer="character", chunk_size=300), text, 60)
    # Each section starts a chunk; the short ones join the section before
    # them while the chunk size allows.
    assert [chunk.split("\n", 1)[0] for chunk in chunks] == ["# Remote work", "# Equipment"]
    assert chunks[1].endswith("# Short\nA.\n# Shorter\nB.")
    assert all(text[start : start + len(chunk)] == chunk for chunk, start in zip(chunks, starts, strict=True))


def test_structured_files_keep_every_line():
    csv = "id,status\n12\nyes\nyes\nyes"
    assert basic_clean(csv, structured=True) == csv


def _chunks():
    text = "\n".join(f"Row {i % 7}: status active, amount 100." for i in range(300))
    chunks, starts = _split_text(RecursiveChunker(tokenizer="character", chunk_size=300), text, 60)
    return text, dict(enumerate(zip(chunks, starts, strict=True)))


def test_excerpts_with_offsets_are_exact_slices():
    text, chunks = _chunks()
    runs = build_excerpt(chunks, [5, 40], 5000).split("\n…\n")
    assert len(runs) == 2 and all(run in text for run in runs)


def test_excerpts_respect_the_budget():
    _, chunks = _chunks()
    assert len(build_excerpt(chunks, [20], 700)) <= 700
