"""Search index: collection setup, model changes, keyword search, and Qdrant failures."""

import httpx
import pytest
from conftest import run
from fakes import SharedQdrant
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from exceptions import AppError


def _rag(client=None):
    from services.search.rag import Rag

    return Rag(client or SharedQdrant())


def test_collection_is_created_once_with_the_model_size(infra):
    rag = _rag(infra.qdrant)
    run(rag.ensure_collection())
    run(rag.ensure_collection())
    info = run(infra.qdrant.get_collection("documents"))
    assert info.config.params.vectors.size == 384


def test_an_empty_collection_follows_a_new_embedding_model(infra):
    run(infra.qdrant.create_collection("documents", vectors_config=VectorParams(size=768, distance=Distance.COSINE)))
    run(_rag(infra.qdrant).ensure_collection())
    assert run(infra.qdrant.get_collection("documents")).config.params.vectors.size == 384


def test_a_filled_collection_refuses_another_model(infra):
    run(infra.qdrant.create_collection("documents", vectors_config=VectorParams(size=768, distance=Distance.COSINE)))
    run(infra.qdrant.upsert("documents", [PointStruct(id=1, vector=[0.1] * 768, payload={})]))
    with pytest.raises(AppError) as conflict:
        run(_rag(infra.qdrant).ensure_collection())
    assert conflict.value.status_code == 409 and "size 768" in conflict.value.message


def test_search_and_lookups_on_a_missing_collection_are_empty(infra):
    rag = _rag(infra.qdrant)
    assert run(rag.search([0.1] * 384, allowed_classifications=["standard"])) == []
    assert run(rag.search([0.1] * 384, allowed_classifications=[])) == []
    run(rag.delete_document(1))  # nothing to delete: no error


def test_search_respects_clearance(infra):
    rag = _rag(infra.qdrant)
    vector = [1.0] + [0.0] * 383
    for document_id, classification in ((1, "standard"), (2, "secret")):
        run(
            rag.upsert_chunks(
                document_id=document_id,
                name="n",
                filename="f.txt",
                classification=classification,
                chunks=["text"],
                vectors=[vector],
                starts=[0],
                indexed=["text"],
            )
        )
    found = run(rag.search(vector, allowed_classifications=["standard"]))
    assert [hit.document_id for hit in found] == [1] and found[0].text == "text"


def test_a_collection_without_the_keyword_index_is_refused_once_filled(infra):
    run(infra.qdrant.create_collection("documents", vectors_config=VectorParams(size=384, distance=Distance.COSINE)))
    run(infra.qdrant.upsert("documents", [PointStruct(id=1, vector=[0.1] * 384, payload={})]))
    with pytest.raises(AppError) as conflict:
        run(_rag(infra.qdrant).ensure_collection())
    assert conflict.value.status_code == 409 and "keyword index" in conflict.value.message


def test_names_and_codes_are_found_by_keyword_even_far_in_meaning(infra):
    rag = _rag(infra.qdrant)
    near, far = [1.0] + [0.0] * 383, [0.0, 1.0] + [0.0] * 382
    rows = {1: ("Warranty of laptops is three years.", near), 2: ("LT-3044\tThinkPad\t2027-03-14", far)}
    for document_id, (text, vector) in rows.items():
        run(
            rag.upsert_chunks(
                document_id=document_id,
                name="n",
                filename="f.txt",
                classification="standard",
                chunks=[text],
                vectors=[vector],
                starts=[0],
                indexed=[text],
            )
        )

    found = run(
        rag.search(
            near, question="When does the warranty of LT-3044 end?", allowed_classifications=["standard"], limit=1
        )
    )
    by_document = {hit.document_id: hit for hit in found}
    assert by_document[2].exact and by_document[2].score == 0.0  # far in meaning
    assert not by_document[1].exact  # found by meaning only


def test_identifiers_are_codes_numbers_and_names():
    from services.search.keywords import holds, identifiers

    assert identifiers("What is the phone extension of Greta Weber?") == [("greta", "weber")]
    assert identifiers("When does LT-3044 expire in 2027?") == [("lt", "3044"), ("2027",)]
    assert identifiers("how many days off do I get") == []
    # Word for word: the two names in different rows do not count.
    assert holds("E1,Greta Weber,Legal", [("greta", "weber")])
    assert not holds("E1,Greta Novak\nE2,Hugo Weber", [("greta", "weber")])


class _Broken:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def __getattr__(self, name):
        async def fail(*args, **kwargs):
            raise self.error

        return fail


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (httpx.ConnectError("refused"), "unavailable"),
        (UnexpectedResponse(403, "Forbidden", b"", httpx.Headers()), "forbidden"),
        (UnexpectedResponse(500, "Error", b"", httpx.Headers()), "unavailable"),
    ],
)
def test_qdrant_failures_become_clear_errors(error, code):
    rag = _rag(_Broken(error))
    for call in (
        rag.ensure_collection(),
        rag.search([0.1] * 384, allowed_classifications=["standard"]),
        rag.delete_document(1),
        rag.chunks_by_index(1, [0]),
    ):
        with pytest.raises(AppError) as raised:
            run(call)
        assert raised.value.code == code


def test_qdrant_connection_settings_are_checked(monkeypatch):
    from services.search.rag import _qdrant_client

    monkeypatch.setenv("QDRANT_PORT", "http")
    with pytest.raises(AppError, match="port"):
        _qdrant_client()
    monkeypatch.setenv("QDRANT_HOST", "")
    with pytest.raises(AppError, match="host"):
        _qdrant_client()
