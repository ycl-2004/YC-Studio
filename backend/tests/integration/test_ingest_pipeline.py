"""Stage 1 Step 7 acceptance checks against a migrated PostgreSQL database.

The unit suite proves control flow against mocks. These prove the things only a real
database can: the composite unique constraint, PostgreSQL's bind-parameter ceiling,
the vector column round-tripping, and the retrieval indexes actually existing.
"""

import math
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chunk import Chunk
from app.db.models.collection import Collection, CollectionKind, CollectionScope
from app.db.models.document import Document
from app.db.models.source import IngestStatus, Source
from app.rag.parsers.factory import UnsupportedFileTypeError
from app.services.ingest_service import (
    _bulk_insert_chunks,
    compute_content_hash,
    ingest_document,
)
from tests.support import local_embedding_model_available

requires_local_model = pytest.mark.skipif(
    not local_embedding_model_available(),
    reason="embedding model is not in the local HuggingFace cache",
)

CASE_FILE = """# 小红书爆款拆解

这是一篇用于测试摄取流水线的案例文章。它需要足够长，才能被切成多个块。

## 选题角度

选题决定了内容的天花板。同样的信息，换一个角度讲，打开率可以差好几倍。
写之前先问三个问题：读者是谁、他现在卡在哪、这篇看完他能立刻做什么。

## 结构安排

开头三行决定用户是否继续读下去。中间用小标题分段，每段只讲一件事。
结尾给一个可以立刻执行的动作，而不是空泛的总结。

## 语言风格

短句优先，少用形容词。能用数字的地方不要用"很多""非常"这类模糊表达。
""".encode()

RULE_FILE = """# 小红书平台规则

1. 单篇正文不超过 1000 字。
2. 标题不超过 20 个字。
3. 禁止出现绝对化用语。
4. 图片不少于 3 张，首图为封面。
""".encode()


async def _create_collection(
    session: AsyncSession,
    kind: CollectionKind = CollectionKind.CASE,
) -> Collection:
    """Insert a private collection to ingest into."""

    collection = Collection(
        user_id=None,
        kind=kind,
        scope=CollectionScope.PRIVATE,
        name=f"test-{kind.value}-{uuid4().hex[:8]}",
    )
    session.add(collection)
    await session.flush()
    return collection


def _fake_embedding(seed: int, dim: int = 768) -> list[float]:
    """A normalized vector that varies per seed, so rows are not all identical."""

    raw = [math.sin(seed + index) for index in range(dim)]
    norm = math.sqrt(sum(value * value for value in raw))
    return [value / norm for value in raw]


async def _count_chunks(session: AsyncSession, collection_id: UUID) -> int:
    total = await session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.collection_id == collection_id)
    )
    return int(total or 0)


async def test_duplicate_content_hash_violates_unique_constraint(
    db_session: AsyncSession,
) -> None:
    """Stage 1 Step 1 acceptance: the composite unique constraint rejects a re-upload."""

    collection = await _create_collection(db_session)
    content_hash = compute_content_hash(b"identical bytes")

    db_session.add(
        Source(
            collection_id=collection.id,
            filename="first.md",
            content_hash=content_hash,
            ingest_status=IngestStatus.COMPLETED,
        )
    )
    await db_session.flush()

    db_session.add(
        Source(
            collection_id=collection.id,
            filename="second-upload-of-the-same-bytes.md",
            content_hash=content_hash,
            ingest_status=IngestStatus.PENDING,
        )
    )
    with pytest.raises(IntegrityError, match="uq_sources_collection_content_hash"):
        await db_session.flush()


async def test_same_hash_allowed_in_a_different_collection(db_session: AsyncSession) -> None:
    """content_hash is unique per collection, so one file may join several libraries."""

    case_collection = await _create_collection(db_session, CollectionKind.CASE)
    material_collection = await _create_collection(db_session, CollectionKind.MATERIAL)
    content_hash = compute_content_hash(b"shared across libraries")

    db_session.add_all(
        [
            Source(
                collection_id=case_collection.id,
                filename="shared.md",
                content_hash=content_hash,
                ingest_status=IngestStatus.COMPLETED,
            ),
            Source(
                collection_id=material_collection.id,
                filename="shared.md",
                content_hash=content_hash,
                ingest_status=IngestStatus.COMPLETED,
            ),
        ]
    )

    await db_session.flush()  # Must not raise.


async def test_bulk_insert_5000_chunks_against_postgres(db_session: AsyncSession) -> None:
    """Acceptance 2: 5000 rows insert without hitting the 32767 bind-parameter ceiling."""

    collection = await _create_collection(db_session)
    source = Source(
        collection_id=collection.id,
        filename="bulk.md",
        content_hash=compute_content_hash(b"bulk"),
        ingest_status=IngestStatus.EMBEDDING,
    )
    db_session.add(source)
    await db_session.flush()

    document = Document(
        source_id=source.id,
        title="bulk",
        raw_text="bulk",
        meta={},
        parser_version="test",
    )
    db_session.add(document)
    await db_session.flush()

    chunks = [
        Chunk(
            collection_id=collection.id,
            document_id=document.id,
            ordinal=ordinal,
            text=f"chunk {ordinal}",
            token_count=4,
            embedding=_fake_embedding(ordinal),
            embed_model="BAAI/bge-base-zh-v1.5",
            embed_version="sentence-transformers==test",
        )
        for ordinal in range(5000)
    ]

    await _bulk_insert_chunks(db_session, chunks, batch_size=200)

    assert await _count_chunks(db_session, collection.id) == 5000


async def test_retrieval_indexes_exist_after_migration(db_session: AsyncSession) -> None:
    """Acceptance 3 precondition: migration 0004 created both retrieval indexes."""

    result = await db_session.execute(
        text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'chunks'")
    )
    definitions = {row.indexname: row.indexdef for row in result}

    assert "ix_chunks_embedding_hnsw" in definitions
    assert "USING hnsw" in definitions["ix_chunks_embedding_hnsw"]
    assert "vector_cosine_ops" in definitions["ix_chunks_embedding_hnsw"]

    assert "ix_chunks_text_gin" in definitions
    assert "USING gin" in definitions["ix_chunks_text_gin"]
    assert "to_tsvector" in definitions["ix_chunks_text_gin"]


async def test_vector_search_returns_nearest_chunk(db_session: AsyncSession) -> None:
    """A cosine ORDER BY round-trips through the vector column and ranks correctly."""

    collection = await _create_collection(db_session)
    source = Source(
        collection_id=collection.id,
        filename="vectors.md",
        content_hash=compute_content_hash(b"vectors"),
        ingest_status=IngestStatus.COMPLETED,
    )
    db_session.add(source)
    await db_session.flush()

    document = Document(
        source_id=source.id,
        title="vectors",
        raw_text="vectors",
        meta={},
        parser_version="test",
    )
    db_session.add(document)
    await db_session.flush()

    target_vector = _fake_embedding(7)
    db_session.add_all(
        [
            Chunk(
                collection_id=collection.id,
                document_id=document.id,
                ordinal=ordinal,
                text=f"chunk {ordinal}",
                token_count=4,
                embedding=_fake_embedding(ordinal),
                embed_model="BAAI/bge-base-zh-v1.5",
                embed_version="sentence-transformers==test",
            )
            for ordinal in range(20)
        ]
    )
    await db_session.flush()

    nearest = await db_session.scalar(
        select(Chunk)
        .where(Chunk.collection_id == collection.id)
        .order_by(Chunk.embedding.cosine_distance(target_vector))
        .limit(1)
    )

    assert nearest is not None
    assert nearest.ordinal == 7


@requires_local_model
async def test_ingest_then_reingest_short_circuits(db_session: AsyncSession) -> None:
    """Acceptance 1: the second upload adds no source, no document, and no chunk."""

    collection = await _create_collection(db_session, CollectionKind.CASE)

    first = await ingest_document(
        session=db_session,
        collection_id=collection.id,
        filename="case.md",
        file_bytes=CASE_FILE,
    )
    await db_session.flush()

    assert first.skipped is False
    assert first.chunk_count >= 1
    chunk_total_after_first = await _count_chunks(db_session, collection.id)
    assert chunk_total_after_first == first.chunk_count

    second = await ingest_document(
        session=db_session,
        collection_id=collection.id,
        filename="case-renamed.md",
        file_bytes=CASE_FILE,
    )

    assert second.skipped is True
    assert second.source_id == first.source_id
    assert second.document_id is None
    assert await _count_chunks(db_session, collection.id) == chunk_total_after_first

    source_total = await db_session.scalar(
        select(func.count()).select_from(Source).where(Source.collection_id == collection.id)
    )
    assert source_total == 1


@requires_local_model
async def test_document_title_survives_byte_upload(db_session: AsyncSession) -> None:
    """Bytes are staged under the real filename, so the title is never a temp name."""

    collection = await _create_collection(db_session, CollectionKind.MATERIAL)

    result = await ingest_document(
        session=db_session,
        collection_id=collection.id,
        filename="小红书爆款拆解.md",
        file_bytes="正文没有一级标题，所以标题必须来自文件名。\n\n再来一段内容。".encode(),
    )
    await db_session.flush()

    document = await db_session.get(Document, result.document_id)
    assert document is not None
    assert document.title == "小红书爆款拆解"
    assert not document.title.startswith("tmp")


@requires_local_model
async def test_ingested_chunks_are_stamped_and_ordered(db_session: AsyncSession) -> None:
    """Acceptance 4: stored chunks carry the encoder identity and a gapless ordinal."""

    collection = await _create_collection(db_session, CollectionKind.CASE)

    result = await ingest_document(
        session=db_session,
        collection_id=collection.id,
        filename="case.md",
        file_bytes=CASE_FILE,
    )
    await db_session.flush()

    chunks = (
        await db_session.scalars(
            select(Chunk).where(Chunk.document_id == result.document_id).order_by(Chunk.ordinal)
        )
    ).all()

    from app.rag.retriever.embeddings import get_local_embedding

    model_limit = get_local_embedding().max_input_tokens
    assert model_limit is not None

    assert len(chunks) == result.chunk_count
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert chunk.embed_model == "BAAI/bge-base-zh-v1.5"
        assert chunk.embed_version is not None
        assert chunk.embed_version.startswith("sentence-transformers==")
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 768
        assert chunk.token_count > 0
        # token_count is what the encoder consumed, special tokens included, so this
        # is the exact condition under which no chunk was truncated at encode time.
        assert chunk.token_count <= model_limit

    source = await db_session.get(Source, result.source_id)
    assert source is not None
    assert source.ingest_status is IngestStatus.COMPLETED


@requires_local_model
async def test_rule_collection_is_stored_as_one_whole_chunk(db_session: AsyncSession) -> None:
    """Stage 1 Step 5 leftover: rule libraries are stored whole, not split."""

    collection = await _create_collection(db_session, CollectionKind.RULE)

    result = await ingest_document(
        session=db_session,
        collection_id=collection.id,
        filename="rules.md",
        file_bytes=RULE_FILE,
    )
    await db_session.flush()

    assert result.chunk_count == 1

    document = await db_session.get(Document, result.document_id)
    assert document is not None

    chunk = await db_session.scalar(select(Chunk).where(Chunk.document_id == document.id))
    assert chunk is not None
    assert chunk.ordinal == 0
    # The whole-document path must not lose text: the single chunk is the full body.
    assert chunk.text.strip() == document.raw_text.strip()


@requires_local_model
async def test_long_rulebook_is_stored_whole_without_a_truncated_vector(
    db_session: AsyncSession,
) -> None:
    """A rulebook past the encoder's window keeps all its text and gets no vector.

    Embedding it would store a vector for the first 512 tokens and drop the rest with
    no error, which is precisely the outcome Stage 1 Step 5 ruled out.
    """

    from app.rag.retriever.embeddings import get_local_embedding

    collection = await _create_collection(db_session, CollectionKind.RULE)
    long_rulebook = "\n".join(
        f"{number}. 规则条目 {number}：正文不超过一千字，标题不超过二十字，禁止绝对化用语。"
        for number in range(1, 61)
    ).encode()

    result = await ingest_document(
        session=db_session,
        collection_id=collection.id,
        filename="平台规则全集.md",
        file_bytes=long_rulebook,
    )
    await db_session.flush()

    assert result.chunk_count == 1

    chunk = await db_session.scalar(select(Chunk).where(Chunk.document_id == result.document_id))
    assert chunk is not None
    assert chunk.embedding is None
    assert chunk.embed_model is None
    assert chunk.embed_version is None

    # The point of the NULL: the chunk is longer than the encoder could have read.
    model_limit = get_local_embedding().max_input_tokens
    assert model_limit is not None
    assert chunk.token_count > model_limit
    assert "规则条目 60" in chunk.text


@requires_local_model
async def test_retrievable_collections_still_require_a_vector(db_session: AsyncSession) -> None:
    """Only whole-document libraries skip embedding; case and material must not."""

    for kind in (CollectionKind.CASE, CollectionKind.MATERIAL):
        collection = await _create_collection(db_session, kind)
        result = await ingest_document(
            session=db_session,
            collection_id=collection.id,
            filename=f"{kind.value}.md",
            file_bytes=CASE_FILE,
        )
        await db_session.flush()

        chunks = (
            await db_session.scalars(select(Chunk).where(Chunk.document_id == result.document_id))
        ).all()
        assert chunks
        for chunk in chunks:
            assert chunk.embedding is not None, f"{kind.value} chunks must stay searchable"
            assert chunk.embed_model == "BAAI/bge-base-zh-v1.5"
            assert chunk.embed_version


@requires_local_model
async def test_failed_ingest_records_status_and_error(db_session: AsyncSession) -> None:
    """A parser failure leaves a failed source row and no orphan document."""

    collection = await _create_collection(db_session, CollectionKind.CASE)

    with pytest.raises(UnsupportedFileTypeError):
        await ingest_document(
            session=db_session,
            collection_id=collection.id,
            filename="broken.xlsx",
            file_bytes=b"not really a spreadsheet",
        )

    source = await db_session.scalar(select(Source).where(Source.collection_id == collection.id))
    assert source is not None
    assert source.ingest_status is IngestStatus.FAILED
    assert source.error_message

    document_total = await db_session.scalar(
        select(func.count()).select_from(Document).where(Document.source_id == source.id)
    )
    assert document_total == 0
