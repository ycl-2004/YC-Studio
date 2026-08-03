import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> app/core -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parents[2]

# This selector is intentionally read before Settings is constructed. An empty value
# disables dotenv loading, which keeps automated tests independent from backend/.env.
_env_file_override = os.getenv("YCSTUDIO_ENV_FILE")
SETTINGS_ENV_FILE: Path | None = (
    BACKEND_DIR / ".env"
    if _env_file_override is None
    else Path(_env_file_override).expanduser()
    if _env_file_override.strip()
    else None
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and an optional dotenv file."""

    model_config = SettingsConfigDict(
        env_file=SETTINGS_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "YC Studio"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api"
    readiness_timeout_seconds: float = Field(default=1.0, gt=0, le=10.0)
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    upload_storage_dir: Path = BACKEND_DIR / "data" / "uploads"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
        ]
    )

    # Database
    database_url: str
    database_host_override: str | None = None
    database_port_override: int | None = Field(default=None, ge=1, le=65535)
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_timeout: float = Field(default=30.0, gt=0)

    # Redis
    redis_url: str
    redis_host_override: str | None = None
    redis_port_override: int | None = Field(default=None, ge=1, le=65535)

    # LLM
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # Embedding
    embedding_provider: str = "huggingface"
    embedding_model: str = "BAAI/bge-base-zh-v1.5"
    embedding_dimension: int = 768
    embedding_device: str = "auto"
    embedding_batch_size: int = Field(default=32, ge=1, le=1024)
    embedding_local_files_only: bool = True

    # RAG
    # Counted with the embedding model's own tokenizer, special tokens included — not
    # characters. Ingestion caps this at the model's own max input length, so a value
    # larger than the encoder's window is corrected with a warning rather than silently
    # truncated. 512 matches bge-base-zh-v1.5 exactly; overlap is the usual 10%.
    chunk_size: int = 512
    chunk_overlap: int = 51
    chunk_method: str = "recursive"
    retrieval_top_k: int = 5
    similarity_threshold: float = 0.65

    # Ingestion
    ingest_batch_size: int = Field(default=200, ge=1, le=1000)

    @model_validator(mode="after")
    def apply_dependency_host_overrides(self) -> "Settings":
        """Replace host-only development URLs when running on a container network."""

        if self.database_host_override is not None:
            self.database_url = _replace_url_host(
                self.database_url,
                self.database_host_override,
                self.database_port_override or 5432,
            )
        if self.redis_host_override is not None:
            self.redis_url = _replace_url_host(
                self.redis_url,
                self.redis_host_override,
                self.redis_port_override or 6379,
            )
        return self


def _replace_url_host(url: str, host: str, port: int) -> str:
    """Preserve credentials/path/query while replacing one dependency endpoint."""

    parts = urlsplit(url)
    credentials, separator, _ = parts.netloc.rpartition("@")
    prefix = f"{credentials}{separator}" if separator else ""
    return urlunsplit(parts._replace(netloc=f"{prefix}{host}:{port}"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""

    return Settings()  # type: ignore[call-arg]  # values are loaded from env/.env
