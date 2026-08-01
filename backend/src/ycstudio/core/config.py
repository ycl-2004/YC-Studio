from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "YC Studio"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
        ]
    )

    # Database
    database_url: str

    # Redis
    redis_url: str

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
    embedding_device: str = "cpu"
    embedding_local_files_only: bool = True

    # RAG
    chunk_size: int = 800
    chunk_overlap: int = 120
    chunk_method: str = "recursive"
    retrieval_top_k: int = 5
    similarity_threshold: float = 0.65


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""

    return Settings()  # type: ignore[call-arg]  # values are loaded from env/.env
