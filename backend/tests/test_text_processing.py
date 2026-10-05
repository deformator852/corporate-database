"""Cleanup rules, long-document excerpts."""

from chonkie import RecursiveChunker

from services.chat import build_excerpt
from services.documents.processor import _split_text
from services.documents.text_cleanup import basic_clean, repeated_lines


def test_rules_drop_page_furniture_but_keep_content():
    text = "Report\n2025\nRevenue grew by 12%.\n- 4 -\nPage 5 of 20\nACME\nx\nACME\ny\nACME\nSee sec-\ntion 3."
    cleaned = basic_clean(text)
    assert "2025" in cleaned and "12%" in cleaned and "section 3." in cleaned
    assert "- 4 -" not in cleaned and "Page 5" not in cleaned and "ACME" not in cleaned


def test_a_chunk_drops_the_headers_of_its_whole_document():
    document = "ACME internal\nBudget is 500 EUR.\nACME internal\nTrips need approval.\nACME internal\nEnd."
    chunk = "ACME internal\nBudget is 500 EUR."  # the header shows once here
    assert basic_clean(chunk, repeated=repeated_lines(document)) == "Budget is 500 EUR."


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
