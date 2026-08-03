"""Stage 1 Step 11 acceptance checks for version-controlled public libraries."""

from pathlib import Path
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chunk import Chunk
from app.db.models.collection import Collection, CollectionKind, CollectionScope
from app.db.models.document import Document
from app.db.models.source import IngestStatus, Source
from app.db.models.user import User
from app.services.public_seed import SeedSummary, seed_public_libraries


async def _seed_collection(session: AsyncSession, kind: CollectionKind) -> Collection:
    collection = await session.scalar(
        select(Collection).where(
            Collection.user_id.is_(None),
            Collection.kind == kind,
        )
    )
    assert collection is not None
    return collection


async def _counts(session: AsyncSession) -> tuple[int, int, int, int]:
    """Count the public-library records that must stay stable on a no-op rerun."""

    collection_count = await session.scalar(
        select(func.count())
        .select_from(Collection)
        .where(Collection.scope == CollectionScope.PUBLIC)
    )
    source_count = await session.scalar(
        select(func.count())
        .select_from(Source)
        .join(Collection, Source.collection_id == Collection.id)
        .where(Collection.scope == CollectionScope.PUBLIC)
    )
    document_count = await session.scalar(
        select(func.count())
        .select_from(Document)
        .join(Source, Document.source_id == Source.id)
        .join(Collection, Source.collection_id == Collection.id)
        .where(Collection.scope == CollectionScope.PUBLIC)
    )
    chunk_count = await session.scalar(
        select(func.count())
        .select_from(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .join(Collection, Source.collection_id == Collection.id)
        .where(Collection.scope == CollectionScope.PUBLIC)
    )
    return (
        int(collection_count or 0),
        int(source_count or 0),
        int(document_count or 0),
        int(chunk_count or 0),
    )


async def _sources_with_documents(
    session: AsyncSession,
    collection_id: UUID,
) -> dict[str, tuple[Source, Document]]:
    rows = await session.execute(
        select(Source, Document)
        .join(Document, Document.source_id == Source.id)
        .where(Source.collection_id == collection_id)
    )
    return {source.filename: (source, document) for source, document in rows}


async def _create_user(session: AsyncSession) -> User:
    user = User(email=f"seed-test-{uuid4().hex}@example.com")
    session.add(user)
    await session.flush()
    return user


async def test_public_seed_is_idempotent_and_updates_only_changed_file(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Two runs are no-ops; one changed Markdown keeps its source identity and refreshes only it."""

    seed_root = tmp_path / "seeds"
    rules = seed_root / "rules"
    templates = seed_root / "templates"
    rules.mkdir(parents=True)
    templates.mkdir()
    rule_a = rules / "audience.md"
    rule_a.write_text("# Audience\n\nUse concrete language.", encoding="utf-8")
    (rules / "claims.md").write_text("# Claims\n\nDo not invent evidence.", encoding="utf-8")
    (templates / "brief.md").write_text("# Brief\n\nState the audience first.", encoding="utf-8")

    first = await seed_public_libraries(db_session, seed_root=seed_root)
    assert first == SeedSummary(2, 3, 0, 0)
    counts_before = await _counts(db_session)
    assert counts_before == (2, 3, 3, 3)

    rule_collection = await _seed_collection(db_session, CollectionKind.RULE)
    sources_before = await _sources_with_documents(db_session, rule_collection.id)
    changed_before, changed_document_before = sources_before["audience.md"]
    changed_source_id = changed_before.id
    changed_content_hash = changed_before.content_hash
    changed_document_id = changed_document_before.id
    stable_before, stable_document_before = sources_before["claims.md"]
    stable_source_id = stable_before.id
    stable_content_hash = stable_before.content_hash
    stable_document_id = stable_document_before.id
    assert all(
        source.ingest_status is IngestStatus.COMPLETED for source, _ in sources_before.values()
    )
    assert all(
        chunk.embedding is None
        for chunk in await _public_rule_chunks(db_session, rule_collection.id)
    )

    second = await seed_public_libraries(db_session, seed_root=seed_root)
    assert second == SeedSummary(0, 0, 0, 3)
    assert await _counts(db_session) == counts_before

    rule_a.write_text("# Audience\n\nUse direct, concrete language.", encoding="utf-8")
    third = await seed_public_libraries(db_session, seed_root=seed_root)
    assert third == SeedSummary(0, 0, 1, 2)
    assert await _counts(db_session) == counts_before

    sources_after = await _sources_with_documents(db_session, rule_collection.id)
    changed_after, changed_document_after = sources_after["audience.md"]
    stable_after, stable_document_after = sources_after["claims.md"]
    assert changed_after.id == changed_source_id
    assert changed_after.content_hash != changed_content_hash
    assert changed_document_after.id != changed_document_id
    assert stable_after.id == stable_source_id
    assert stable_after.content_hash == stable_content_hash
    assert stable_document_after.id == stable_document_id


async def _public_rule_chunks(session: AsyncSession, collection_id: UUID) -> list[Chunk]:
    return list(await session.scalars(select(Chunk).where(Chunk.collection_id == collection_id)))


async def test_seed_frontmatter_never_reaches_stored_content(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """A seed file's YAML frontmatter must not leak into what gets injected as a prompt.

    Rule and template collections are injected whole into prompts (ADR decision 16), so
    anything left in Document.raw_text is live model input, not documentation.
    """

    seed_root = tmp_path / "seeds"
    (seed_root / "rules").mkdir(parents=True)
    (seed_root / "templates").mkdir()
    (seed_root / "rules" / "baseline.md").write_text(
        "---\nseed_version: 1\nlibrary: public-rules\n---\n\n"
        "# Baseline\n\nNever fabricate a source.",
        encoding="utf-8",
    )
    (seed_root / "templates" / "brief.md").write_text("# Brief\n\nState the ask.", encoding="utf-8")

    await seed_public_libraries(db_session, seed_root=seed_root)

    rule_collection = await _seed_collection(db_session, CollectionKind.RULE)
    _source, document = (await _sources_with_documents(db_session, rule_collection.id))[
        "baseline.md"
    ]

    assert document.raw_text.startswith("# Baseline")
    assert "seed_version" not in document.raw_text
    assert "---" not in document.raw_text
    assert document.title == "Baseline"


async def test_seeded_public_libraries_reject_both_upload_routes(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Only the checked-in seed workflow writes public collections, never either HTTP upload API."""

    seed_root = tmp_path / "seeds"
    (seed_root / "rules").mkdir(parents=True)
    (seed_root / "templates").mkdir()
    (seed_root / "rules" / "baseline.md").write_text("# Baseline", encoding="utf-8")
    (seed_root / "templates" / "brief.md").write_text("# Brief", encoding="utf-8")
    await seed_public_libraries(db_session, seed_root=seed_root)
    public_rules = await _seed_collection(db_session, CollectionKind.RULE)
    user = await _create_user(db_session)

    form = {
        "collection_id": str(public_rules.id),
        "kind": "rule",
        "platform": "general",
        "content_type": "rule",
    }
    headers = {"X-User-ID": str(user.id)}
    single = await client.post(
        "/api/kb/upload",
        files={"file": ("attempt.md", b"# Attempt", "text/markdown")},
        data=form,
        headers=headers,
    )
    batch = await client.post(
        "/api/kb/batch-upload",
        files=[("files", ("attempt.md", b"# Attempt", "text/markdown"))],
        data=form,
        headers=headers,
    )

    assert single.status_code == 403
    assert batch.status_code == 403
    assert "Only the owner" in single.json()["detail"]
    assert "Only the owner" in batch.json()["detail"]
