"""Keyword search next to vector search. Vectors match meaning but are weak
on exact strings - codes ("LT-3044"), contract numbers, names - which
company questions are full of. Chunks are also indexed by their words
(sparse vectors, scored BM25-style by Qdrant with IDF), and a chunk found
this way counts as relevant when it holds every name and code of the
question, word for word.

Word ids are keyed digests: the index does not reveal which words a
confidential document contains. After a key rotation, documents indexed
before it no longer match new queries by keyword (vector search still does).
"""

import re
from collections import Counter

from qdrant_client.http.models import SparseVector

from encryption import keyed_digest

_WORD = re.compile(r"\w+")
# BM25 term-frequency saturation: the 5th "invoice" in a chunk adds little.
_K1 = 1.2


def words(text: str) -> list[str]:
    return [word for word in _WORD.findall(text.casefold()) if len(word) > 1 or word.isdigit()]


def _word_id(word: str) -> int:
    return int.from_bytes(keyed_digest(b"word:" + word.encode())[:4], "big")


def _sparse(weights: dict[int, float]) -> SparseVector:
    return SparseVector(indices=list(weights), values=list(weights.values()))


def chunk_keywords(text: str) -> SparseVector:
    weights: dict[int, float] = {}
    for word, count in Counter(words(text)).items():
        index = _word_id(word)
        weights[index] = weights.get(index, 0.0) + count * (_K1 + 1) / (count + _K1)
    return _sparse(weights)


def query_keywords(text: str) -> SparseVector:
    return _sparse({_word_id(word): 1.0 for word in set(words(text))})


def identifiers(question: str) -> list[tuple[str, ...]]:
    """Names and codes in the question, as phrases: words with a digit
    ("LT-3044", "2025") or capitalized past the first word ("Greta Weber",
    "VPN"); neighbours joined by a space or hyphen form one phrase."""
    phrases: list[list[str]] = []
    end = -1
    for index, match in enumerate(_WORD.finditer(question)):
        word = match.group()
        if not (any(char.isdigit() for char in word) or (index > 0 and len(word) > 1 and word[0].isupper())):
            continue
        if phrases and question[end : match.start()] in {" ", "-"}:
            phrases[-1].append(word.casefold())
        else:
            phrases.append([word.casefold()])
        end = match.end()
    return [tuple(phrase) for phrase in phrases]


def holds(text: str, phrases: list[tuple[str, ...]]) -> bool:
    """Whether every phrase appears in `text`, its words in a row."""
    line = f" {' '.join(words(text))} "
    return all(f" {' '.join(phrase)} " in line for phrase in phrases)
