"""Unit tests for Stage 1 Step 7: hashing, dedup short-circuit, and batched inserts.

These mock the session and the embedding model so the pipeline's control flow is
covered without a database or a model download. The database-backed acceptance
checks live in tests/integration/test_ingest_pipeline.py.
"""

import hashlib
import math
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.db.models.chunk import Chunk
from app.db.models.collection import Collection, CollectionKind, CollectionScope
from app.db.models.source import IngestStatus, Source
from app.services.ingest_service import (
    _bulk_insert_chunks,
    _fit_chunk_budget,
    compute_content_hash,
    ingest_document,
)

EMBED_MODEL = "BAAI/bge-base-zh-v1.5"
EMBED_VERSION = "sentence-transformers==5.6.1"
MODEL_MAX_INPUT_TOKENS = 512


def _fake_embedding(dim: int = 768) -> list[float]:
    """Build a deterministic normalized vector of the production dimension."""

    raw = [1.0 / (index + 1) for index in range(dim)]
    norm = math.sqrt(sum(value * value for value in raw))
    return [value / norm for value in raw]


def _make_chunk(ordinal: int, document_id: UUID, collection_id: UUID) -> Chunk:
    return Chunk(
        collection_id=collection_id,
        document_id=document_id,
        ordinal=ordinal,
        text=f"Chunk {ordinal} text content for testing",
        token_count=10,
        embedding=_fake_embedding(),
        embed_model=EMBED_MODEL,
        embed_version=EMBED_VERSION,
    )


def _mock_session() -> AsyncMock:
    """An AsyncSession stand-in whose synchronous methods stay synchronous."""

    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    return session


def _mock_collection(collection_id: UUID, kind: CollectionKind = CollectionKind.CASE) -> Collection:
    return Collection(
        id=collection_id,
        user_id=None,
        kind=kind,
        scope=CollectionScope.PRIVATE,
        name="test-collection",
    )


def test_compute_content_hash_matches_sha256():
    """The dedup key is a plain SHA-256 hex digest of the raw bytes."""

    data = b"hello world test file content"

    assert compute_content_hash(data) == hashlib.sha256(data).hexdigest()
    assert len(compute_content_hash(data)) == 64


def test_compute_content_hash_is_deterministic():
    """Identical content must hash identically or dedup never fires."""

    assert compute_content_hash(b"identical content") == compute_content_hash(b"identical content")


def test_compute_content_hash_separates_different_content():
    """Different content must not collide into a false duplicate."""

    assert compute_content_hash(b"file A") != compute_content_hash(b"file B")


def test_chunk_budget_left_alone_when_it_fits():
    """A configured budget within the model's window passes through untouched."""

    assert _fit_chunk_budget(512, 51, MODEL_MAX_INPUT_TOKENS) == (512, 51)
    assert _fit_chunk_budget(256, 25, MODEL_MAX_INPUT_TOKENS) == (256, 25)


def test_chunk_budget_capped_at_the_model_window():
    """An oversized budget is capped, keeping the configured overlap ratio."""

    fitted_max, fitted_overlap = _fit_chunk_budget(4000, 400, MODEL_MAX_INPUT_TOKENS)

    assert fitted_max == MODEL_MAX_INPUT_TOKENS
    assert fitted_overlap == int(MODEL_MAX_INPUT_TOKENS * 0.1)
    # TextChunker rejects an overlap that is not smaller than the chunk size.
    assert fitted_overlap < fitted_max


def test_chunk_budget_survives_an_extreme_overlap_ratio():
    """Even a near-100% configured overlap stays constructible after capping."""

    fitted_max, fitted_overlap = _fit_chunk_budget(4000, 3999, MODEL_MAX_INPUT_TOKENS)

    assert fitted_max == MODEL_MAX_INPUT_TOKENS
    assert fitted_overlap < fitted_max


def test_chunk_budget_respects_config_when_model_limit_unknown():
    """A backend that exposes no window leaves the configured budget in charge."""

    assert _fit_chunk_budget(4000, 400, None) == (4000, 400)


async def test_ingest_duplicate_file_short_circuits():
    """Acceptance 1: a second upload of the same bytes returns before any parsing."""

    collection_id = uuid4()
    file_bytes = b"# Test Document\n\nThis is test content."
    existing_source = Source(
        collection_id=collection_id,
        filename="test.md",
        content_hash=compute_content_hash(file_bytes),
        ingest_status=IngestStatus.COMPLETED,
    )

    session = _mock_session()
    dedup_result = MagicMock()
    dedup_result.scalar_one_or_none.return_value = existing_source
    session.execute.return_value = dedup_result

    result = await ingest_document(
        session=session,
        collection_id=collection_id,
        filename="test.md",
        file_bytes=file_bytes,
    )

    assert result.skipped is True
    assert result.source_id == existing_source.id
    assert result.document_id is None
    assert result.chunk_count == 0
    # No source row, no savepoint, no chunk inserts: the short circuit did no work.
    session.add.assert_not_called()
    session.add_all.assert_not_called()
    session.begin_nested.assert_not_called()


async def test_bulk_insert_splits_5000_chunks_into_batches():
    """Acceptance 2: 5000 chunks are inserted as bounded batches, not one statement."""

    session = _mock_session()
    document_id, collection_id = uuid4(), uuid4()
    chunks = [_make_chunk(index, document_id, collection_id) for index in range(5000)]

    await _bulk_insert_chunks(session, chunks, batch_size=200)

    assert session.add_all.call_count == 25
    assert session.flush.await_count == 25


async def test_bulk_insert_last_batch_holds_the_remainder():
    """A non-multiple batch count must not drop or duplicate the trailing rows."""

    session = _mock_session()
    document_id, collection_id = uuid4(), uuid4()
    chunks = [_make_chunk(index, document_id, collection_id) for index in range(550)]

    await _bulk_insert_chunks(session, chunks, batch_size=200)

    assert session.add_all.call_count == 3
    inserted = [chunk for call in session.add_all.call_args_list for chunk in call.args[0]]
    assert len(inserted) == 550
    assert len(session.add_all.call_args_list[-1].args[0]) == 150


async def test_every_chunk_carries_embed_model_and_version():
    """Acceptance 4: the encoder identity is stamped on each chunk at write time."""

    collection_id = uuid4()
    session = _mock_session()
    dedup_result = MagicMock()
    dedup_result.scalar_one_or_none.return_value = None
    session.execute.return_value = dedup_result
    session.get.return_value = _mock_collection(collection_id)

    embedding = MagicMock()
    embedding.embed_model = EMBED_MODEL
    embedding.embed_version = EMBED_VERSION
    embedding.max_input_tokens = MODEL_MAX_INPUT_TOKENS

    with (
        patch("app.services.ingest_service.encode_texts", return_value=[_fake_embedding()]),
        patch("app.services.ingest_service.get_local_embedding", return_value=embedding),
    ):
        result = await ingest_document(
            session=session,
            collection_id=collection_id,
            filename="test.md",
            file_bytes=b"# Test\n\nSome content for embedding test.",
            count_tokens=len,
        )

    assert result.skipped is False
    assert result.chunk_count == 1

    inserted = [
        chunk
        for call in session.add_all.call_args_list
        for chunk in call.args[0]
        if isinstance(chunk, Chunk)
    ]
    assert inserted
    for chunk in inserted:
        assert chunk.embed_model == EMBED_MODEL
        assert chunk.embed_version == EMBED_VERSION


async def test_pipeline_failure_marks_source_failed_and_reraises():
    """A mid-pipeline failure rolls back to the savepoint but records the failure."""

    collection_id = uuid4()
    session = _mock_session()
    dedup_result = MagicMock()
    dedup_result.scalar_one_or_none.return_value = None
    session.execute.return_value = dedup_result
    session.get.return_value = _mock_collection(collection_id)
    savepoint = AsyncMock()
    savepoint.is_active = True
    session.begin_nested.return_value = savepoint

    with (
        patch("app.services.ingest_service.get_local_embedding", return_value=MagicMock()),
        patch(
            "app.services.ingest_service._parse_upload",
            side_effect=RuntimeError("parser exploded"),
        ),
        pytest.raises(RuntimeError, match="parser exploded"),
    ):
        await ingest_document(
            session=session,
            collection_id=collection_id,
            filename="broken.md",
            file_bytes=b"whatever",
            count_tokens=len,
        )

    savepoint.rollback.assert_awaited_once()
    savepoint.commit.assert_not_awaited()
    # One dedup SELECT plus the status UPDATE written after the rollback.
    assert session.execute.await_count == 2
