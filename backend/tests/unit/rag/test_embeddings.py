"""Unit tests for Stage 1 Step 6: embedding contract, device resolution, and batching."""

import math
import time
from unittest.mock import patch

import pytest

from app.rag.retriever.embeddings import (
    BaseEmbedding,
    clear_embeddings_cache,
    get_local_embedding,
    resolve_device,
)
from tests.support import local_embedding_model_available

# Loading bge-base-zh-v1.5 needs a warmed HuggingFace cache. CI has none and
# settings default to local_files_only, so these skip there and run locally.
requires_local_model = pytest.mark.skipif(
    not local_embedding_model_available(),
    reason="embedding model is not in the local HuggingFace cache",
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
    with (
        patch("torch.cuda.is_available", return_value=False),
        patch("torch.backends.mps.is_available", return_value=True),
    ):
        assert resolve_device("auto") == "mps"


def test_resolve_device_auto_cpu_fallback():
    """Auto device selection should fallback to cpu when CUDA and MPS are unavailable."""
    with (
        patch("torch.cuda.is_available", return_value=False),
        patch("torch.backends.mps.is_available", return_value=False),
    ):
        assert resolve_device("auto") == "cpu"


@requires_local_model
def test_singleton_cache_second_call_no_reload():
    """Acceptance 1: the second call returns the cached singleton without reloading."""
    first_instance = get_local_embedding()
    second_instance = get_local_embedding()

    assert isinstance(first_instance, BaseEmbedding)
    assert first_instance is second_instance


@requires_local_model
def test_embedding_dimension_768():
    """Acceptance 2: output dimension is exactly 768, matching Vector(768) in the schema."""
    emb = get_local_embedding()
    vector = emb.embed_query("测试文本维度")
    assert len(vector) == 768


@requires_local_model
def test_vector_normalization_l2():
    """Acceptance 4: the L2 norm is ~1.0, so cosine distance is well defined."""
    emb = get_local_embedding()
    vectors = emb.encode_texts(["测试向量归一化"], normalize_embeddings=True)
    assert len(vectors) == 1

    l2_norm = math.sqrt(sum(x * x for x in vectors[0]))
    assert math.isclose(l2_norm, 1.0, abs_tol=1e-4)


@requires_local_model
def test_batch_encoding_faster_than_sequential():
    """Acceptance 3: encoding 100 texts in one batch beats 100 sequential calls."""
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

    assert duration_batch < duration_seq, (
        f"Batch ({duration_batch:.3f}s) should be faster than Sequential ({duration_seq:.3f}s)"
    )
