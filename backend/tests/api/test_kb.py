"""Stage 1 Step 8/10 HTTP contracts against the real database fixture."""

from types import SimpleNamespace
from uuid import UUID, uuid4

from httpx import AsyncClient
from pytest import MonkeyPatch, mark
from sqlalchemy.ext.asyncio import AsyncSession

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
    fake_embedding = FakeEmbedding()
    monkeypatch.setattr(
        "app.services.ingest_service.get_local_embedding",
        lambda: fake_embedding,
    )
    monkeypatch.setattr(
        "app.services.ingest_service.encode_texts",
        lambda texts, **_: [_vector(1.0) for _ in texts],
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
