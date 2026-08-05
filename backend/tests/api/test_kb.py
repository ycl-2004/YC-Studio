"""Stage 1 Step 8/10 HTTP contracts against the real database fixture."""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from httpx import AsyncClient
from pytest import MonkeyPatch, mark
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import LocalUploadStorage
from app.db.models.chunk import Chunk
from app.db.models.collection import Collection, CollectionKind, CollectionScope
from app.db.models.document import Document
from app.db.models.source import IngestStatus, Source
from app.db.models.user import User
from app.rag.parsers.factory import ParserFactory

# What a real client actually puts on the wire for each parsable suffix.  Declared
# independently of the API's own table so the two cannot drift into agreement by accident;
# a newly registered parser makes the parametrized case below fail with KeyError.
_CLIENT_CONTENT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "application/octet-stream",
    ".txt": "text/plain",
    ".htm": "text/html",
    ".html": "text/html",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class FakeEmbedding:
    """Deterministic embedding boundary that keeps HTTP tests offline and fast."""

    max_input_tokens = 512
    embed_model = "test-embedding"
    embed_version = "test-embedding==1"

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def embed_query(self, text: str) -> list[float]:
        del text
        return _vector(1.0)


def _vector(first_value: float) -> list[float]:
    return [first_value, *([0.0] * 767)]


async def _private_collection(
    session: AsyncSession,
    *,
    owner_id: UUID,
    kind: CollectionKind = CollectionKind.MATERIAL,
) -> Collection:
    collection = Collection(
        user_id=owner_id,
        kind=kind,
        scope=CollectionScope.PRIVATE,
        name=f"{kind.value}-{uuid4().hex}",
    )
    session.add(collection)
    await session.flush()
    return collection


async def _user(session: AsyncSession, label: str) -> User:
    user = User(email=f"{label}-{uuid4().hex}@example.com")
    session.add(user)
    await session.flush()
    return user


def _install_fake_ingest_embedding(monkeypatch: MonkeyPatch) -> None:
    """Stub every module-level ``get_local_embedding`` import, not just one.

    ``ingest_service`` and ``kb_service`` each did ``from ... import get_local_embedding``,
    so each holds its own name bound to the real function; patching one leaves the other
    untouched. A test that only patches ingest_service and then calls the search endpoint
    hits the real model loader — which works by accident on a machine with the model
    cached and fails with an unhandled 500 anywhere else, CI included.
    """

    fake_embedding = FakeEmbedding()
    monkeypatch.setattr(
        "app.services.ingest_service.get_local_embedding",
        lambda: fake_embedding,
    )
    monkeypatch.setattr(
        "app.services.ingest_service.encode_texts",
        lambda texts, **_: [_vector(1.0) for _ in texts],
    )
    monkeypatch.setattr(
        "app.services.kb_service.get_local_embedding",
        lambda: fake_embedding,
    )


async def test_upload_rejects_unsupported_suffix_before_ingest(client: AsyncClient) -> None:
    response = await client.post(
        "/api/kb/upload",
        files={"file": ("malware.exe", b"not a document", "application/x-msdownload")},
        data={
            "collection_id": str(uuid4()),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(uuid4())},
    )

    assert response.status_code == 422
    assert "Unsupported file type .exe" in response.json()["detail"]


def test_every_parsable_suffix_has_upload_content_types() -> None:
    """A format the parsers accept must never be unreachable through the upload route."""

    # Imported inside the test because module-level app imports would freeze the cached
    # settings before the infrastructure fixture publishes the container URLs.
    from app.api.kb import _MIME_TYPES_BY_SUFFIX

    assert set(ParserFactory.supported_suffixes()) == set(_MIME_TYPES_BY_SUFFIX)
    assert set(_CLIENT_CONTENT_TYPES) == set(_MIME_TYPES_BY_SUFFIX)


@mark.parametrize("suffix", ParserFactory.supported_suffixes())
async def test_upload_admits_every_parsable_suffix(client: AsyncClient, suffix: str) -> None:
    """Each parsable suffix clears filename/content-type validation and reaches the service.

    The collection does not exist, so 404 proves the request got past validation; a 422
    would mean the format is rejected before any parser ever sees it.
    """

    response = await client.post(
        "/api/kb/upload",
        files={"file": (f"document{suffix}", b"content", _CLIENT_CONTENT_TYPES[suffix])},
        data={
            "collection_id": str(uuid4()),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(uuid4())},
    )

    assert response.status_code == 404, response.text


async def test_upload_rejects_a_content_type_that_contradicts_the_suffix(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/kb/upload",
        files={"file": ("report.pdf", b"%PDF-1.7", "text/html")},
        data={
            "collection_id": str(uuid4()),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(uuid4())},
    )

    assert response.status_code == 422
    assert "is not valid for .pdf" in response.json()["detail"]
    assert "application/pdf" in response.json()["detail"]


async def test_upload_rejects_an_oversized_file(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    import app.api.kb as kb_api

    monkeypatch.setattr(kb_api, "get_settings", lambda: SimpleNamespace(upload_max_bytes=3))
    response = await client.post(
        "/api/kb/upload",
        files={"file": ("too-large.md", b"four", "text/markdown")},
        data={
            "collection_id": str(uuid4()),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(uuid4())},
    )

    assert response.status_code == 422
    assert "3-byte upload limit" in response.json()["detail"]


async def test_upload_ingests_owned_private_collection_and_returns_document(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
) -> None:
    _install_fake_ingest_embedding(monkeypatch)
    user = await _user(db_session, "owner")
    collection = await _private_collection(db_session, owner_id=user.id)

    response = await client.post(
        "/api/kb/upload",
        files={
            "file": (
                "ideas.md",
                b"# Useful idea\n\nThe document is ingested through the HTTP route.",
                "text/markdown",
            )
        },
        data={
            "collection_id": str(collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(user.id)},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert UUID(body["source_id"])
    assert UUID(body["document_id"])
    assert body["chunk_count"] == 1
    assert body["skipped"] is False
    document = await db_session.get(Document, UUID(body["document_id"]))
    assert document is not None
    assert document.meta["platform"] == "general"
    assert document.meta["content_type"] == "tutorial"


async def test_upload_rejects_someone_elses_private_collection(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner = await _user(db_session, "owner")
    stranger = await _user(db_session, "stranger")
    collection = await _private_collection(db_session, owner_id=owner.id)

    response = await client.post(
        "/api/kb/upload",
        files={"file": ("notes.md", b"# Private", "text/markdown")},
        data={
            "collection_id": str(collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(stranger.id)},
    )

    assert response.status_code == 403
    assert "Only the owner" in response.json()["detail"]


async def test_upload_rejects_public_collection(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, "private-writer")
    public_collection = Collection(
        user_id=None,
        kind=CollectionKind.MATERIAL,
        scope=CollectionScope.PUBLIC,
        name=f"public-{uuid4().hex}",
    )
    db_session.add(public_collection)
    await db_session.flush()

    response = await client.post(
        "/api/kb/upload",
        files={"file": ("notes.md", b"# Public", "text/markdown")},
        data={
            "collection_id": str(public_collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(user.id)},
    )

    assert response.status_code == 403
    assert "Only the owner" in response.json()["detail"]


async def test_search_returns_provenance_applies_metadata_and_rejects_rules(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_embedding = FakeEmbedding()
    monkeypatch.setattr("app.services.kb_service.get_local_embedding", lambda: fake_embedding)
    user = await _user(db_session, "searcher")
    collection = await _private_collection(
        db_session,
        owner_id=user.id,
        kind=CollectionKind.CASE,
    )
    source = Source(
        collection_id=collection.id,
        filename="case-study.md",
        content_hash="f" * 64,
        ingest_status=IngestStatus.COMPLETED,
    )
    db_session.add(source)
    await db_session.flush()
    matching_document = Document(
        source_id=source.id,
        title="Matched document",
        raw_text="Matched text",
        meta={"platform": "xiaohongshu"},
        parser_version="test",
    )
    db_session.add(matching_document)
    await db_session.flush()
    db_session.add_all(
        [
            Chunk(
                collection_id=collection.id,
                document_id=matching_document.id,
                ordinal=0,
                text="The closest chunk",
                token_count=3,
                embedding=_vector(1.0),
                embed_model="test",
                embed_version="test",
            ),
            Chunk(
                collection_id=collection.id,
                document_id=matching_document.id,
                ordinal=1,
                text="The distant chunk",
                token_count=3,
                embedding=_vector(-1.0),
                embed_model="test",
                embed_version="test",
            ),
        ]
    )
    await db_session.flush()
    other_collection = await _private_collection(
        db_session,
        owner_id=user.id,
        kind=CollectionKind.MATERIAL,
    )
    other_source = Source(
        collection_id=other_collection.id,
        filename="material.md",
        content_hash="e" * 64,
        ingest_status=IngestStatus.COMPLETED,
    )
    db_session.add(other_source)
    await db_session.flush()
    other_document = Document(
        source_id=other_source.id,
        title="Material document",
        raw_text="Material text",
        meta={"platform": "xiaohongshu"},
        parser_version="test",
    )
    db_session.add(other_document)
    await db_session.flush()
    db_session.add(
        Chunk(
            collection_id=other_collection.id,
            document_id=other_document.id,
            ordinal=0,
            text="A material chunk that must not appear in a case search",
            token_count=3,
            embedding=_vector(1.0),
            embed_model="test",
            embed_version="test",
        )
    )
    await db_session.flush()

    response = await client.post(
        "/api/kb/search",
        json={
            "query": "closest",
            "kind": "case",
            "top_k": 1,
            "metadata_filter": {"platform": "xiaohongshu"},
        },
        headers={"X-User-ID": str(user.id)},
    )

    assert response.status_code == 200, response.text
    result = response.json()["results"]
    assert len(result) == 1
    assert result[0]["text"] == "The closest chunk"
    assert result[0]["score"] == 1.0
    assert result[0]["document"]["id"] == str(matching_document.id)
    assert result[0]["source"]["id"] == str(source.id)
    assert result[0]["source"]["filename"] == "case-study.md"

    unsupported = await client.post(
        "/api/kb/search",
        json={"query": "rules", "kind": "rule"},
        headers={"X-User-ID": str(user.id)},
    )
    assert unsupported.status_code == 422
    assert "not searchable" in unsupported.json()["detail"]


async def test_list_collections_shows_public_and_private(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, "owner")
    private = await _private_collection(db_session, owner_id=user.id, kind=CollectionKind.CASE)
    public = Collection(
        user_id=None,
        kind=CollectionKind.RULE,
        scope=CollectionScope.PUBLIC,
        name=f"rules-{uuid4().hex}",
    )
    db_session.add(public)
    await db_session.flush()

    response = await client.get("/api/kb/collections", headers={"X-User-ID": str(user.id)})

    assert response.status_code == 200, response.text
    bodies = response.json()["collections"]
    ids = {collection["id"] for collection in bodies}
    assert str(private.id) in ids
    assert str(public.id) in ids
    mine = next(c for c in bodies if c["id"] == str(private.id))
    assert mine["scope"] == "private"
    assert mine["source_count"] == 0
    assert mine["document_count"] == 0
    assert mine["chunk_count"] == 0


async def test_list_collections_filters_by_kind(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, "owner")
    await _private_collection(db_session, owner_id=user.id, kind=CollectionKind.CASE)
    await _private_collection(db_session, owner_id=user.id, kind=CollectionKind.MATERIAL)

    response = await client.get(
        "/api/kb/collections",
        params={"kind": "material"},
        headers={"X-User-ID": str(user.id)},
    )

    assert response.status_code == 200, response.text
    bodies = response.json()["collections"]
    assert len(bodies) == 1
    assert bodies[0]["kind"] == "material"


async def test_create_collection_appears_in_list(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, "owner")
    payload = {"kind": "material", "name": "我的素材库"}

    created = await client.post(
        "/api/kb/collections", json=payload, headers={"X-User-ID": str(user.id)}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["scope"] == "private"
    assert body["name"] == "我的素材库"
    assert body["user_id"] == str(user.id)

    listed = await client.get("/api/kb/collections", headers={"X-User-ID": str(user.id)})
    assert listed.status_code == 200
    assert any(c["id"] == body["id"] for c in listed.json()["collections"])


async def test_create_collection_rejects_duplicate(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, "owner")
    payload = {"kind": "material", "name": "dup"}

    first = await client.post(
        "/api/kb/collections", json=payload, headers={"X-User-ID": str(user.id)}
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/api/kb/collections", json=payload, headers={"X-User-ID": str(user.id)}
    )
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


async def test_list_sources_shows_ingested_document(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
) -> None:
    _install_fake_ingest_embedding(monkeypatch)
    user = await _user(db_session, "owner")
    collection = await _private_collection(
        db_session, owner_id=user.id, kind=CollectionKind.MATERIAL
    )
    upload = await client.post(
        "/api/kb/upload",
        files={"file": ("ideas.md", b"# Idea\n\nThe content is ingested.", "text/markdown")},
        data={
            "collection_id": str(collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(user.id)},
    )
    assert upload.status_code == 201, upload.text

    response = await client.get(
        f"/api/kb/collections/{collection.id}/sources",
        headers={"X-User-ID": str(user.id)},
    )
    assert response.status_code == 200, response.text
    sources = response.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["filename"] == "ideas.md"
    assert sources[0]["ingest_status"] == "completed"
    assert sources[0]["chunk_count"] == 1
    assert sources[0]["title"] is not None


async def test_list_sources_rejects_other_private_collection(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner = await _user(db_session, "owner")
    stranger = await _user(db_session, "stranger")
    collection = await _private_collection(db_session, owner_id=owner.id)

    response = await client.get(
        f"/api/kb/collections/{collection.id}/sources",
        headers={"X-User-ID": str(stranger.id)},
    )
    assert response.status_code == 403
    assert "Only the owner" in response.json()["detail"]


async def test_list_sources_404_for_missing_collection(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, "searcher")
    response = await client.get(
        f"/api/kb/collections/{uuid4()}/sources",
        headers={"X-User-ID": str(user.id)},
    )
    assert response.status_code == 404


async def test_delete_source_removes_chunk_and_excludes_from_search(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_embedding = FakeEmbedding()
    monkeypatch.setattr("app.services.kb_service.get_local_embedding", lambda: fake_embedding)
    user = await _user(db_session, "owner")
    collection = await _private_collection(db_session, owner_id=user.id, kind=CollectionKind.CASE)
    source = Source(
        collection_id=collection.id,
        filename="case.md",
        content_hash="a" * 64,
        ingest_status=IngestStatus.COMPLETED,
    )
    db_session.add(source)
    await db_session.flush()
    document = Document(
        source_id=source.id,
        title="Case document",
        raw_text="Matched text",
        meta={"platform": "xiaohongshu"},
        parser_version="test",
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        Chunk(
            collection_id=collection.id,
            document_id=document.id,
            ordinal=0,
            text="The closest chunk",
            token_count=3,
            embedding=_vector(1.0),
            embed_model="test",
            embed_version="test",
        )
    )
    await db_session.flush()

    before = await client.post(
        "/api/kb/search",
        json={"query": "closest", "kind": "case", "top_k": 5},
        headers={"X-User-ID": str(user.id)},
    )
    assert before.status_code == 200, before.text
    assert len(before.json()["results"]) == 1

    deleted = await client.delete(
        f"/api/kb/sources/{source.id}", headers={"X-User-ID": str(user.id)}
    )
    assert deleted.status_code == 204

    after = await client.post(
        "/api/kb/search",
        json={"query": "closest", "kind": "case", "top_k": 5},
        headers={"X-User-ID": str(user.id)},
    )
    assert after.status_code == 200, after.text
    assert len(after.json()["results"]) == 0


async def test_delete_source_rejects_public_collection(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, "writer")
    public = Collection(
        user_id=None,
        kind=CollectionKind.MATERIAL,
        scope=CollectionScope.PUBLIC,
        name=f"public-{uuid4().hex}",
    )
    db_session.add(public)
    await db_session.flush()
    source = Source(
        collection_id=public.id,
        filename="p.md",
        content_hash="b" * 64,
        ingest_status=IngestStatus.COMPLETED,
    )
    db_session.add(source)
    await db_session.flush()

    response = await client.delete(
        f"/api/kb/sources/{source.id}", headers={"X-User-ID": str(user.id)}
    )
    assert response.status_code == 403
    assert "Only the owner" in response.json()["detail"]


def _install_temporary_upload_storage(monkeypatch: MonkeyPatch, root: Path) -> None:
    """Point both the writing (API) and reading (service) sides at one scratch directory.

    Each module imported ``LocalUploadStorage`` by name, so patching only one leaves the
    other writing to — or reading from — the developer's real backend/data/uploads.
    """

    def storage_factory() -> LocalUploadStorage:
        return LocalUploadStorage(root)

    monkeypatch.setattr("app.api.kb.LocalUploadStorage", storage_factory)
    monkeypatch.setattr("app.services.kb_service.LocalUploadStorage", storage_factory)


def test_every_parsable_suffix_has_a_served_media_type() -> None:
    """A stored format must always be previewable or at least downloadable."""

    from app.api.kb import _SERVED_FILE_BY_SUFFIX
    from app.schemas.kb import SourcePreviewMode

    assert set(ParserFactory.supported_suffixes()) == set(_SERVED_FILE_BY_SUFFIX)
    # Uploaded markup is never served as HTML from the API origin, or a stored file
    # could run script against it.
    for suffix in (".htm", ".html"):
        media_type, mode = _SERVED_FILE_BY_SUFFIX[suffix]
        assert media_type.startswith("text/plain")
        assert mode is SourcePreviewMode.DOWNLOAD


async def test_preview_returns_file_facts_parsed_text_and_chunks(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_ingest_embedding(monkeypatch)
    _install_temporary_upload_storage(monkeypatch, tmp_path)
    user = await _user(db_session, "previewer")
    collection = await _private_collection(db_session, owner_id=user.id)
    file_bytes = b"# Preview me\n\nThe original bytes are kept for the drawer."

    upload = await client.post(
        "/api/kb/upload",
        files={"file": ("preview.md", file_bytes, "text/markdown")},
        data={
            "collection_id": str(collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(user.id)},
    )
    assert upload.status_code == 201, upload.text
    source_id = upload.json()["source_id"]

    response = await client.get(
        f"/api/kb/sources/{source_id}/preview",
        headers={"X-User-ID": str(user.id)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filename"] == "preview.md"
    assert body["suffix"] == ".md"
    assert body["preview_mode"] == "text"
    assert body["ingest_status"] == "completed"
    assert body["original_available"] is True
    assert body["size_bytes"] == len(file_bytes)
    assert body["document_id"] == upload.json()["document_id"]
    assert "The original bytes are kept for the drawer." in body["raw_text"]
    assert body["raw_text_truncated"] is False
    assert body["chunk_count"] == 1
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["ordinal"] == 0
    assert body["chunks_truncated"] is False


async def test_preview_reports_a_missing_original_but_keeps_parsed_text(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Seeded public libraries have parsed text and no stored file; both routes say so."""

    _install_temporary_upload_storage(monkeypatch, tmp_path)
    user = await _user(db_session, "seed-reader")
    public = Collection(
        user_id=None,
        kind=CollectionKind.RULE,
        scope=CollectionScope.PUBLIC,
        name=f"public-{uuid4().hex}",
    )
    db_session.add(public)
    await db_session.flush()
    source = Source(
        collection_id=public.id,
        filename="baseline.md",
        content_hash="c" * 64,
        ingest_status=IngestStatus.COMPLETED,
    )
    db_session.add(source)
    await db_session.flush()
    db_session.add(
        Document(
            source_id=source.id,
            title="Baseline",
            raw_text="The parsed text survives without the original upload.",
            meta={},
            parser_version="test",
        )
    )
    await db_session.flush()

    preview = await client.get(
        f"/api/kb/sources/{source.id}/preview",
        headers={"X-User-ID": str(user.id)},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["original_available"] is False
    assert body["size_bytes"] is None
    assert body["raw_text"] == "The parsed text survives without the original upload."
    assert body["chunk_count"] == 0

    file_response = await client.get(
        f"/api/kb/sources/{source.id}/file",
        headers={"X-User-ID": str(user.id)},
    )
    assert file_response.status_code == 404
    assert "only its parsed text is available" in file_response.json()["detail"]


async def test_source_file_serves_the_stored_original_inline_and_as_attachment(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_ingest_embedding(monkeypatch)
    _install_temporary_upload_storage(monkeypatch, tmp_path)
    user = await _user(db_session, "downloader")
    collection = await _private_collection(db_session, owner_id=user.id)
    file_bytes = b"# Original\n\nByte-for-byte what was uploaded."

    upload = await client.post(
        "/api/kb/upload",
        files={"file": ("original.md", file_bytes, "text/markdown")},
        data={
            "collection_id": str(collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(user.id)},
    )
    assert upload.status_code == 201, upload.text
    source_id = upload.json()["source_id"]

    inline = await client.get(
        f"/api/kb/sources/{source_id}/file",
        headers={"X-User-ID": str(user.id)},
    )
    assert inline.status_code == 200, inline.text
    assert inline.content == file_bytes
    assert inline.headers["content-type"].startswith("text/markdown")
    assert inline.headers["content-disposition"].startswith("inline")
    assert inline.headers["x-content-type-options"] == "nosniff"

    attachment = await client.get(
        f"/api/kb/sources/{source_id}/file",
        params={"download": "true"},
        headers={"X-User-ID": str(user.id)},
    )
    assert attachment.status_code == 200, attachment.text
    assert attachment.headers["content-disposition"].startswith("attachment")


async def test_preview_and_file_reject_someone_elses_private_collection(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_temporary_upload_storage(monkeypatch, tmp_path)
    owner = await _user(db_session, "owner")
    stranger = await _user(db_session, "stranger")
    collection = await _private_collection(db_session, owner_id=owner.id)
    source = Source(
        collection_id=collection.id,
        filename="private.md",
        content_hash="d" * 64,
        ingest_status=IngestStatus.COMPLETED,
    )
    db_session.add(source)
    await db_session.flush()

    for path in (f"/api/kb/sources/{source.id}/preview", f"/api/kb/sources/{source.id}/file"):
        response = await client.get(path, headers={"X-User-ID": str(stranger.id)})
        assert response.status_code == 403, response.text
        assert "Only the owner" in response.json()["detail"]


async def test_preview_404_after_the_source_is_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_ingest_embedding(monkeypatch)
    _install_temporary_upload_storage(monkeypatch, tmp_path)
    user = await _user(db_session, "deleter")
    collection = await _private_collection(db_session, owner_id=user.id)
    upload = await client.post(
        "/api/kb/upload",
        files={"file": ("gone.md", b"# Gone\n\nSoon soft-deleted.", "text/markdown")},
        data={
            "collection_id": str(collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(user.id)},
    )
    assert upload.status_code == 201, upload.text
    source_id = upload.json()["source_id"]

    deleted = await client.delete(
        f"/api/kb/sources/{source_id}", headers={"X-User-ID": str(user.id)}
    )
    assert deleted.status_code == 204

    response = await client.get(
        f"/api/kb/sources/{source_id}/preview",
        headers={"X-User-ID": str(user.id)},
    )
    assert response.status_code == 404


async def test_preview_404_for_an_unknown_source(client: AsyncClient) -> None:
    response = await client.get(
        f"/api/kb/sources/{uuid4()}/preview",
        headers={"X-User-ID": str(uuid4())},
    )
    assert response.status_code == 404


async def test_create_collection_reports_an_unknown_principal_not_a_duplicate(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A UUID that names no user must not be reported as a name conflict.

    Both failures arrive as IntegrityError; only the SQLSTATE distinguishes the
    foreign key on kb_collections.user_id from the owner/kind/name unique index.
    """

    del db_session  # The fixture supplies the transaction the endpoint runs in.
    response = await client.post(
        "/api/kb/collections",
        json={"kind": "material", "name": f"orphan-{uuid4().hex}"},
        headers={"X-User-ID": str(uuid4())},
    )

    assert response.status_code == 401, response.text
    detail = response.json()["detail"]
    assert "does not exist" in detail
    assert "already exists" not in detail


async def test_create_collection_still_reports_a_real_duplicate_as_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """The 23505 path keeps its 409 now that 23503 has its own answer."""

    user = await _user(db_session, "duplicate-owner")
    payload = {"kind": "material", "name": f"dup-{uuid4().hex}"}

    first = await client.post(
        "/api/kb/collections", json=payload, headers={"X-User-ID": str(user.id)}
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/kb/collections", json=payload, headers={"X-User-ID": str(user.id)}
    )
    assert second.status_code == 409, second.text
    assert "already exists" in second.json()["detail"]


async def test_upload_retries_a_failed_source_instead_of_skipping_it(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A file whose first ingest failed must be uploadable again.

    Deduplication keys on (collection, content hash) alone, so a failed row used to
    make the identical bytes permanently unacceptable: the retry returned
    ``skipped: true`` and the user's only workaround was to edit the file.
    """

    from app.services.ingest_service import compute_content_hash

    _install_fake_ingest_embedding(monkeypatch)
    _install_temporary_upload_storage(monkeypatch, tmp_path)
    user = await _user(db_session, "retrier")
    collection = await _private_collection(db_session, owner_id=user.id)
    file_bytes = b"# Retry me\n\nThe first attempt failed before this document existed."

    failed_source = Source(
        collection_id=collection.id,
        filename="retry.md",
        content_hash=compute_content_hash(file_bytes),
        ingest_status=IngestStatus.FAILED,
        error_message="the embedding model was unavailable",
    )
    db_session.add(failed_source)
    await db_session.flush()

    response = await client.post(
        "/api/kb/upload",
        files={"file": ("retry.md", file_bytes, "text/markdown")},
        data={
            "collection_id": str(collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        headers={"X-User-ID": str(user.id)},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["skipped"] is False
    assert body["document_id"] is not None
    assert body["chunk_count"] == 1
    # The retry reuses the row, because (collection_id, content_hash) is unique.
    assert body["source_id"] == str(failed_source.id)

    listed = await client.get(
        f"/api/kb/collections/{collection.id}/sources",
        headers={"X-User-ID": str(user.id)},
    )
    sources = listed.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["ingest_status"] == "completed"


async def test_upload_can_re_add_a_soft_deleted_file(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Re-uploading a deleted file must restore it, not hit the unique index.

    ``uq_sources_collection_content_hash`` does not exclude soft-deleted rows, so an
    insert of the same bytes would raise IntegrityError and surface as a 500.
    """

    _install_fake_ingest_embedding(monkeypatch)
    _install_temporary_upload_storage(monkeypatch, tmp_path)
    user = await _user(db_session, "restorer")
    collection = await _private_collection(db_session, owner_id=user.id)
    file_bytes = b"# Deleted then restored\n\nThe same bytes come back."
    upload_payload = {
        "files": {"file": ("restore.md", file_bytes, "text/markdown")},
        "data": {
            "collection_id": str(collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
        },
        "headers": {"X-User-ID": str(user.id)},
    }

    first = await client.post("/api/kb/upload", **upload_payload)
    assert first.status_code == 201, first.text
    source_id = first.json()["source_id"]

    deleted = await client.delete(
        f"/api/kb/sources/{source_id}", headers={"X-User-ID": str(user.id)}
    )
    assert deleted.status_code == 204

    again = await client.post("/api/kb/upload", **upload_payload)

    assert again.status_code == 201, again.text
    body = again.json()
    assert body["skipped"] is False
    assert body["chunk_count"] == 1

    listed = await client.get(
        f"/api/kb/collections/{collection.id}/sources",
        headers={"X-User-ID": str(user.id)},
    )
    sources = listed.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["ingest_status"] == "completed"
    assert sources[0]["filename"] == "restore.md"
