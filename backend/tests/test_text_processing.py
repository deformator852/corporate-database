"""Cleanup rules, rewrite safety, long-document excerpts."""

from chonkie import RecursiveChunker

from services.chat import build_excerpt
from services.documents.processor import _split_text
from services.documents.text_cleanup import basic_clean, rewrite_is_safe


def test_rules_drop_page_furniture_but_keep_content():
    text = "Report\n2025\nRevenue grew by 12%.\n- 4 -\nPage 5 of 20\nACME\nx\nACME\ny\nACME\nSee sec-\ntion 3."
    cleaned = basic_clean(text)
    assert "2025" in cleaned and "12%" in cleaned and "section 3." in cleaned
    assert "- 4 -" not in cleaned and "Page 5" not in cleaned and "ACME" not in cleaned


def test_structured_files_keep_every_line():
    csv = "id,status\n12\nyes\nyes\nyes"
    assert basic_clean(csv, structured=True) == csv


def test_rewrite_must_keep_numbers_and_length():
    assert rewrite_is_safe("Pay 1 250,50 by 5 May", "Pay 1 250,50 by 5 May")
    assert not rewrite_is_safe("Pay 1 250,50 by 5 May", "Pay by May")
    assert not rewrite_is_safe("a" * 100, "a" * 10)


def _chunks(with_offsets: bool):
    text = "\n".join(f"Row {i % 7}: status active, amount 100." for i in range(300))
    chunks, starts = _split_text(RecursiveChunker(tokenizer="character", chunk_size=300), text, 60)
    return text, {i: (c, s if with_offsets else None) for i, (c, s) in enumerate(zip(chunks, starts))}


def test_excerpts_with_offsets_are_exact_slices():
    text, chunks = _chunks(with_offsets=True)
    runs = build_excerpt(chunks, [5, 40], 5000).split("\n…\n")
    assert len(runs) == 2 and all(run in text for run in runs)


def test_excerpts_of_old_chunks_never_lose_text():
    # No offsets (chunks stored before them): on repetitive text a little
    # duplicate may stay, but nothing is dropped.
    _, chunks = _chunks(with_offsets=False)
    excerpt = build_excerpt(chunks, [5, 40], 5000)
    for index in (i for i in (4, 5, 6, 39, 40, 41) if i in chunks):
        for line in chunks[index][0].splitlines()[1:-1]:
            assert line in excerpt


def test_excerpts_respect_the_budget():
    _, chunks = _chunks(True)
    assert len(build_excerpt(chunks, [20], 700)) <= 700
