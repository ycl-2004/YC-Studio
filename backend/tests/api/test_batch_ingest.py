"""Stage 1 Step 9 HTTP/worker acceptance checks with durable real database rows."""

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import LocalUploadStorage
from app.db.models.collection import CollectionKind
from app.db.models.source import IngestStatus, Source
from app.services.kb_service import PendingUpload, create_pending_batch
from tests.api.test_kb import _install_fake_ingest_embedding, _private_collection, _user


async def test_batch_upload_returns_before_work_and_reports_pending_progress(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.api.kb as kb_api

    user = await _user(db_session, "batch-owner")
    collection = await _private_collection(db_session, owner_id=user.id)
    queued: list[UUID] = []

    async def record_enqueue(source_ids: list[UUID]) -> None:
        queued.extend(source_ids)

    monkeypatch.setattr(kb_api, "_enqueue_sources", record_enqueue)
    monkeypatch.setattr(kb_api, "LocalUploadStorage", lambda: LocalUploadStorage(tmp_path))
    response = await client.post(
        "/api/kb/batch-upload",
        files=[
            ("files", ("first.md", b"# First", "text/markdown")),
            ("files", ("second.md", b"# Second", "text/markdown")),
        ],
        data={
            "collection_id": str(collection.id),
            "kind": "material",
            "platform": "general",
            "content_type": "tutorial",
            "dir_paths": ["references/one", "references/two"],
        },
        headers={"X-User-ID": str(user.id)},
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["total"] == 2
    assert queued == [UUID(source_id) for source_id in body["source_ids"]]
    progress = await client.get(
        f"/api/kb/batches/{body['batch_id']}",
        headers={"X-User-ID": str(user.id)},
    )
    assert progress.status_code == 200
    assert progress.json() == {
        "batch_id": body["batch_id"],
        "total": 2,
        "completed": 0,
        "failed": 0,
        "in_progress": 0,
        "pending": 2,
    }
    sources = list(
        await db_session.scalars(select(Source).where(Source.batch_id == UUID(body["batch_id"])))
    )
    assert {source.dir_path for source in sources} == {"references/one", "references/two"}
    assert all(tmp_path.joinpath(str(source.id), source.filename).is_file() for source in sources)


async def test_worker_processes_one_source_and_isolates_a_missing_file_failure(
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.tasks.ingest_tasks import ingest_source

    _install_fake_ingest_embedding(monkeypatch)
    user = await _user(db_session, "worker-owner")
    collection = await _private_collection(db_session, owner_id=user.id)
    batch, sources = await create_pending_batch(
        db_session,
        current_user_id=user.id,
        collection_id=collection.id,
        kind=CollectionKind.MATERIAL,
        metadata={"platform": "general", "content_type": "tutorial"},
        uploads=[
            PendingUpload("good.md", b"# Good", "folder"),
            PendingUpload("missing.md", b"# Missing", "folder"),
        ],
    )
    storage = LocalUploadStorage(tmp_path)
    await storage.save(sources[0].id, sources[0].filename, b"# Good")
    monkeypatch.setattr("app.tasks.ingest_tasks.LocalUploadStorage", lambda: storage)

    @asynccontextmanager
    async def session_factory():
        yield db_session

    monkeypatch.setattr("app.tasks.ingest_tasks.async_session_factory", session_factory)

    completed = await ingest_source({}, str(sources[0].id))
    failed = await ingest_source({}, str(sources[1].id))

    assert completed["chunk_count"] == 1
    assert failed["failed"] is True
    await db_session.refresh(sources[0])
    await db_session.refresh(sources[1])
    assert sources[0].ingest_status is IngestStatus.COMPLETED
    assert sources[1].ingest_status is IngestStatus.FAILED
    assert batch.id == sources[0].batch_id == sources[1].batch_id


async def test_worker_records_failure_when_the_pipeline_fails_after_a_savepoint(
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failure inside ingest_pending_source must not crash the failure handler itself.

    Unlike the missing-file case above, this failure happens *after* the file was read
    and a savepoint opened — ingest_pending_source rolls that back and re-raises, which
    expires the Source instance. A real deployment found this the hard way: the worker
    raised MissingGreenlet instead of recording ``failed``, because the outer handler
    read the expired ``source.id`` instead of the plain id captured before the savepoint.
    """

    from app.tasks.ingest_tasks import ingest_source

    _install_fake_ingest_embedding(monkeypatch)
    user = await _user(db_session, "savepoint-failure-owner")
    collection = await _private_collection(db_session, owner_id=user.id)
    batch, sources = await create_pending_batch(
        db_session,
        current_user_id=user.id,
        collection_id=collection.id,
        kind=CollectionKind.MATERIAL,
        metadata={"platform": "general", "content_type": "tutorial"},
        # .xlsx is unparsable, so failure happens inside _run_pipeline — after PENDING
        # was already committed and PARSING flushed — not while reading storage.
        uploads=[PendingUpload("bad.xlsx", b"not really a spreadsheet", None)],
    )
    storage = LocalUploadStorage(tmp_path)
    await storage.save(sources[0].id, sources[0].filename, b"not really a spreadsheet")
    monkeypatch.setattr("app.tasks.ingest_tasks.LocalUploadStorage", lambda: storage)

    @asynccontextmanager
    async def session_factory():
        yield db_session

    monkeypatch.setattr("app.tasks.ingest_tasks.async_session_factory", session_factory)

    result = await ingest_source({}, str(sources[0].id))

    assert result["failed"] is True
    await db_session.refresh(sources[0])
    assert sources[0].ingest_status is IngestStatus.FAILED
    assert sources[0].error_message
    assert batch.id == sources[0].batch_id


async def test_worker_ingested_chunks_are_searchable_by_dir_path(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Acceptance 5: dir_path must reach Document.meta, or it can never filter a search.

    Source.dir_path is written on upload, but the search endpoint only ever reads
    Document.meta — a folder upload that never copies dir_path into that JSONB column
    would leave "filter search results by folder" permanently unreachable.
    """

    from app.tasks.ingest_tasks import ingest_source

    _install_fake_ingest_embedding(monkeypatch)
    user = await _user(db_session, "dir-path-owner")
    collection = await _private_collection(db_session, owner_id=user.id)
    batch, sources = await create_pending_batch(
        db_session,
        current_user_id=user.id,
        collection_id=collection.id,
        kind=CollectionKind.MATERIAL,
        metadata={"platform": "general", "content_type": "tutorial"},
        uploads=[
            PendingUpload("notes.md", b"# Notes\n\nFolder-scoped content.", "工作笔记/2026"),
            PendingUpload("other.md", b"# Other\n\nRoot-level content.", None),
        ],
    )
    storage = LocalUploadStorage(tmp_path)
    for source, upload in zip(
        sources,
        ["# Notes\n\nFolder-scoped content.", "# Other\n\nRoot-level content."],
        strict=True,
    ):
        await storage.save(source.id, source.filename, upload.encode())
    monkeypatch.setattr("app.tasks.ingest_tasks.LocalUploadStorage", lambda: storage)

    @asynccontextmanager
    async def session_factory():
        yield db_session

    monkeypatch.setattr("app.tasks.ingest_tasks.async_session_factory", session_factory)

    folder_result = await ingest_source({}, str(sources[0].id))
    await ingest_source({}, str(sources[1].id))
    assert folder_result["chunk_count"] == 1
    assert batch.id == sources[0].batch_id

    response = await client.post(
        "/api/kb/search",
        json={
            "query": "folder content",
            "kind": "material",
            "metadata_filter": {"dir_path": "工作笔记/2026"},
        },
        headers={"X-User-ID": str(user.id)},
    )

    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["document"]["id"] == folder_result["document_id"]
