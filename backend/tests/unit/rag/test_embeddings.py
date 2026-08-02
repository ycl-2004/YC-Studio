import math
import os
import time
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LLM_PROVIDER", "test")
os.environ.setdefault("LLM_API_KEY", "test")
os.environ.setdefault("LLM_MODEL", "test")
os.environ.setdefault("LLM_BASE_URL", "http://localhost")

import pytest
from app.rag.retriever.embeddings import (
    BaseEmbedding,
    LocalEmbedding,
    clear_embeddings_cache,
    encode_texts,
    get_embeddings,
    get_local_embedding,
    resolve_device,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_embeddings_cache()
    yield
    clear_embeddings_cache()


def test_resolve_device_explicit():
    """Explicit device settings should be returned as specified."""
    assert resolve_device("cpu") == "cpu"
    assert resolve_device("cuda") == "cuda"
    assert resolve_device("mps") == "mps"
    assert resolve_device("cuda:1") == "cuda:1"


def test_resolve_device_auto_cuda():
    """Auto device selection should prefer cuda when torch.cuda.is_available() is True."""
    with patch("torch.cuda.is_available", return_value=True):
        assert resolve_device("auto") == "cuda"


def test_resolve_device_auto_mps():
    """Auto device selection should prefer mps on Apple Silicon when CUDA is unavailable."""
    with patch("torch.cuda.is_available", return_value=False), patch(
        "torch.backends.mps.is_available", return_value=True
    ):
        assert resolve_device("auto") == "mps"


def test_resolve_device_auto_cpu_fallback():
    """Auto device selection should fallback to cpu when CUDA and MPS are unavailable."""
    with patch("torch.cuda.is_available", return_value=False), patch(
        "torch.backends.mps.is_available", return_value=False
    ):
        assert resolve_device("auto") == "cpu"


def test_singleton_cache_second_call_no_reload():
    """Acceptance Check 1: Second call returns identical cached singleton instance without re-initialization."""
    first_instance = get_local_embedding()
    second_instance = get_local_embedding()

    assert isinstance(first_instance, BaseEmbedding)
    assert first_instance is second_instance


def test_embedding_dimension_768():
    """Acceptance Check 2: Output vector dimension is exactly 768 (bge-base-zh-v1.5 standard)."""
    emb = get_local_embedding()
    vector = emb.embed_query("测试文本维度")
    assert len(vector) == 768


def test_vector_normalization_l2():
    """Acceptance Check 4: Vector L2 norm is approximately 1.0 (normalization effective for cosine distance)."""
    emb = get_local_embedding()
    vectors = emb.encode_texts(["测试向量归一化"], normalize_embeddings=True)
    assert len(vectors) == 1

    l2_norm = math.sqrt(sum(x * x for x in vectors[0]))
    assert math.isclose(l2_norm, 1.0, abs_tol=1e-4)


def test_batch_encoding_faster_than_sequential():
    """Acceptance Check 3: Batch encoding 100 items is measurably faster than 100 sequential individual calls."""
    sample_texts = [
        f"This is sample text number {i} for batch encoding performance evaluation."
        for i in range(100)
    ]
    emb = get_local_embedding()

    # Warmup
    _ = emb.embed_query("warmup")

    # Sequential single calls
    start_seq = time.perf_counter()
    for t in sample_texts:
        _ = emb.embed_query(t)
    duration_seq = time.perf_counter() - start_seq

    # Batch call
    start_batch = time.perf_counter()
    _ = emb.encode_texts(sample_texts, batch_size=32)
    duration_batch = time.perf_counter() - start_batch

    assert (
        duration_batch < duration_seq
    ), f"Batch ({duration_batch:.3f}s) should be faster than Sequential ({duration_seq:.3f}s)"
