"""Helpers shared by unit and integration tests.

Nothing here may touch ``get_settings()``. Skip markers evaluate at collection time,
before the container fixtures publish real service URLs, and ``get_settings`` is
lru_cached — reading it early would freeze the placeholder DATABASE_URL for the whole
session and every database test would connect to nothing.
"""

import functools
import os

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-base-zh-v1.5"


@functools.cache
def local_embedding_model_available() -> bool:
    """Report whether the configured embedding model is already in the HuggingFace cache.

    Settings default to ``embedding_local_files_only=True``, so a machine without a
    warmed cache (CI, a fresh clone) cannot construct ``LocalEmbedding`` at all. Tests
    that need real vectors skip themselves instead of failing on a missing download.
    """

    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import HFValidationError

    model_id = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    try:
        snapshot_download(model_id, local_files_only=True)
    except (OSError, ValueError, HFValidationError):
        return False
    return True
