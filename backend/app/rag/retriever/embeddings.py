"""Embedding model contract, local implementation, and batch text encoding utilities.

Aligns with Stage 1 Step 6 of the YC Studio Architecture.
"""

from abc import ABC, abstractmethod

import structlog
import torch
from langchain_huggingface import HuggingFaceEmbeddings

from app.core.config import get_settings

logger = structlog.stdlib.get_logger(__name__)

_local_embedding_instance: "LocalEmbedding | None" = None


def resolve_device(device_setting: str | None = None) -> str:
    """Automatically resolve target hardware execution device for PyTorch.

    Device selection logic when device is 'auto' (or empty/None):
    1. 'cuda' if NVIDIA CUDA GPU is available (torch.cuda.is_available())
    2. 'mps' if Apple Silicon GPU is available (torch.backends.mps.is_available())
    3. 'cpu' as default fallback.
    """
    settings = get_settings()
    target = (device_setting if device_setting is not None else settings.embedding_device).strip().lower()
    if target == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return target


class BaseEmbedding(ABC):
    """Abstract base contract for text embedding models."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Encode multiple document texts into vector representations."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Encode a single query text into a vector representation."""

    @abstractmethod
    def encode_texts(
        self,
        texts: list[str],
        batch_size: int | None = None,
        normalize_embeddings: bool = True,
    ) -> list[list[float]]:
        """Encode a batch of texts into normalized vector embeddings."""


class LocalEmbedding(BaseEmbedding):
    """Local embedding implementation using HuggingFace / SentenceTransformers.

    Features:
    - Global singleton caching (prevents repeated expensive model loads)
    - Auto-device resolution (Mac mps / CUDA gpu / CPU fallback)
    - Configurable batch size
    - L2 normalization for cosine similarity
    """

    def __init__(self, device: str | None = None, batch_size: int | None = None):
        settings = get_settings()
        provider = settings.embedding_provider.strip().lower()
        if provider != "huggingface":
            raise ValueError(
                f"不支持的 EMBEDDING_PROVIDER: {settings.embedding_provider!r}；"
                "当前仅支持 'huggingface'。"
            )

        self.device = resolve_device(device)
        self.batch_size = batch_size if batch_size is not None else settings.embedding_batch_size
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension

        logger.info(
            "Initializing LocalEmbedding model singleton",
            model_name=self.model_name,
            device=self.device,
            batch_size=self.batch_size,
        )

        self._hf_embeddings = HuggingFaceEmbeddings(
            model_name=self.model_name,
            model_kwargs={
                "device": self.device,
                "local_files_only": settings.embedding_local_files_only,
            },
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": self.batch_size,
            },
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Encode multiple document texts into vector representations."""
        return self._hf_embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Encode a single query text into a vector representation."""
        return self._hf_embeddings.embed_query(text)

    def encode_texts(
        self,
        texts: list[str],
        batch_size: int | None = None,
        normalize_embeddings: bool = True,
    ) -> list[list[float]]:
        """Encode a batch of text strings into vector embeddings."""
        if not texts:
            return []

        effective_batch_size = batch_size if batch_size is not None else self.batch_size

        if hasattr(self._hf_embeddings, "client") and hasattr(self._hf_embeddings.client, "encode"):
            vectors = self._hf_embeddings.client.encode(
                texts,
                batch_size=effective_batch_size,
                normalize_embeddings=normalize_embeddings,
                show_progress_bar=False,
            )
            return vectors.tolist() if hasattr(vectors, "tolist") else [v.tolist() for v in vectors]

        return self._hf_embeddings.embed_documents(texts)


def get_local_embedding(
    force_reload: bool = False,
    device: str | None = None,
    batch_size: int | None = None,
) -> LocalEmbedding:
    """Return configured LocalEmbedding singleton instance."""
    global _local_embedding_instance
    if _local_embedding_instance is not None and not force_reload and device is None and batch_size is None:
        return _local_embedding_instance

    instance = LocalEmbedding(device=device, batch_size=batch_size)
    if device is None and batch_size is None:
        _local_embedding_instance = instance
    return instance


def get_embeddings(
    force_reload: bool = False,
    device: str | None = None,
    batch_size: int | None = None,
) -> HuggingFaceEmbeddings:
    """Return underlying HuggingFaceEmbeddings singleton instance for LangChain compatibility."""
    local_emb = get_local_embedding(force_reload=force_reload, device=device, batch_size=batch_size)
    return local_emb._hf_embeddings


def clear_embeddings_cache() -> None:
    """Clear cached LocalEmbedding singleton instance."""
    global _local_embedding_instance
    _local_embedding_instance = None


def encode_texts(
    texts: list[str],
    batch_size: int | None = None,
    normalize_embeddings: bool = True,
    device: str | None = None,
) -> list[list[float]]:
    """Convenience helper for batch text encoding using LocalEmbedding singleton."""
    if not texts:
        return []
    embedding_service = get_local_embedding(device=device, batch_size=batch_size)
    return embedding_service.encode_texts(
        texts=texts,
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
    )
