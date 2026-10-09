"""Re-chunking after a chunk size change: optional, from the System page,
one document at a time, and the documents stay searchable meanwhile."""

from conftest import csrf, login, process, run, upload

_TEXT = " ".join(f"Clause {n}: the supplier ships part {n} within ten days of the order." for n in range(60)).encode()


def _chunk_indexes(document_id: int) -> list[int]:
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    from services.search.rag import COLLECTION_NAME, Rag

    async def load() -> list[int]:
        records, _ = await Rag().client.scroll(
            COLLECTION_NAME,
            scroll_filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]),
            limit=1000,
        )
        return sorted(record.payload["chunk_index"] for record in records if record.payload)

    return run(load())


def _run_worker_chain() -> list[int]:
    """What `rechunk_next` does, until no document is left."""
    from services.documents.processor import claim_rechunk, rechunk_document_job

    done = []
    while (document_id := run(claim_rechunk())) is not None:
        run(rechunk_document_job(document_id))
        done.append(document_id)
    return done


def _status(client, document_id: int) -> str:
    items = client.get("/api/v1/documents", params={"per_page": 100}).json()["items"]
    return next(item["status"] for item in items if item["id"] == document_id)


def test_documents_are_re_chunked_only_on_request_and_stay_searchable(client, make_user, infra, monkeypatch):
    import settings

    permissions = ["documents.list", "documents.create", "system.view", "system.rechunk", "audit.list"]
    _, email, password = make_user(permissions)
    login(client, email, password)
    size, overlap = str(settings.chunk_size()), str(settings.chunk_overlap())
    document_id = upload(client, "Supply terms", _TEXT, "terms.txt").json()["id"]
    process(document_id)
    before = _chunk_indexes(document_id)
    # Other tests' documents share the database: every count is of them too.
    assert client.get("/api/v1/system/status").json()["outdated_chunks"] == 0

    # A smaller size: old documents keep their chunks until someone asks.
    monkeypatch.setenv("CHUNK_SIZE", "300")
    monkeypatch.setenv("CHUNK_OVERLAP", "50")
    outdated = client.get("/api/v1/system/status").json()["outdated_chunks"]
    assert outdated >= 1
    assert _chunk_indexes(document_id) == before

    started = client.post("/api/v1/system/rechunk", headers=csrf(client))
    assert started.json() == {"documents": outdated} and infra.queue.rechunks == 1
    assert _status(client, document_id) == "completed"  # the chat still uses it
    # One rebuild at a time.
    assert client.post("/api/v1/system/rechunk", headers=csrf(client)).status_code == 409

    assert document_id in _run_worker_chain()
    smaller = _chunk_indexes(document_id)
    assert len(smaller) > len(before) and smaller == list(range(len(smaller)))
    assert _status(client, document_id) == "completed"
    assert client.get("/api/v1/system/status").json()["outdated_chunks"] == 0

    # Back to the larger size: the chunks past the new count go.
    monkeypatch.setenv("CHUNK_SIZE", size)
    monkeypatch.setenv("CHUNK_OVERLAP", overlap)
    client.post("/api/v1/system/rechunk", headers=csrf(client))
    _run_worker_chain()
    assert _chunk_indexes(document_id) == before

    actions = client.get("/api/v1/audit", params={"action": "system.rechunk", "q": email}).json()["items"]
    assert [entry["details"] for entry in actions] == [{"documents": outdated}, {"documents": outdated}]


def test_nothing_to_re_chunk_starts_no_work(client, make_user, infra):
    _, email, password = make_user(["system.rechunk"])
    login(client, email, password)
    client.post("/api/v1/system/rechunk", headers=csrf(client))
    _run_worker_chain()  # whatever other tests left
    started = infra.queue.rechunks
    assert client.post("/api/v1/system/rechunk", headers=csrf(client)).json() == {"documents": 0}
    assert infra.queue.rechunks == started


def test_re_chunking_needs_its_permission(client, make_user):
    _, email, password = make_user(["system.view"])
    login(client, email, password)
    assert client.post("/api/v1/system/rechunk", headers=csrf(client)).status_code == 403
