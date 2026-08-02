"""Rebuild the chunks retrieval indexes and measure what they buy.

Usage:
    uv run python scripts/build_indexes.py [--probes N] [--top-k K]

Stage 1 Step 7 acceptance: run a retrieval benchmark without the indexes, build them
while timing each one, then run the identical benchmark again. The latency delta is a
Stage 3 baseline; the build time is what a full re-embed will cost.

Query vectors are sampled from the chunks already stored, so the script needs a
populated database but not the embedding model.
"""

import argparse
import asyncio
import time
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings
from app.db.models.chunk import FULLTEXT_REGCONFIG, HNSW_EF_CONSTRUCTION, HNSW_M

logger = structlog.stdlib.get_logger(__name__)

DEFAULT_PROBES = 20
DEFAULT_TOP_K = 8

CREATE_HNSW = f"""
    CREATE INDEX ix_chunks_embedding_hnsw
    ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})
"""

CREATE_GIN = f"""
    CREATE INDEX ix_chunks_text_gin
    ON chunks
    USING gin (to_tsvector('{FULLTEXT_REGCONFIG}', text))
"""


@dataclass(frozen=True, slots=True)
class LatencyReport:
    """Per-query latency in milliseconds across a fixed set of probe queries."""

    probes: int
    vector_mean_ms: float
    vector_p95_ms: float
    fulltext_mean_ms: float

    @staticmethod
    def _percentile(sorted_samples: list[float], fraction: float) -> float:
        if not sorted_samples:
            return 0.0
        index = min(int(len(sorted_samples) * fraction), len(sorted_samples) - 1)
        return sorted_samples[index]

    @classmethod
    def from_samples(cls, vector_ms: list[float], fulltext_ms: list[float]) -> "LatencyReport":
        return cls(
            probes=len(vector_ms),
            vector_mean_ms=sum(vector_ms) / len(vector_ms) if vector_ms else 0.0,
            vector_p95_ms=cls._percentile(sorted(vector_ms), 0.95),
            fulltext_mean_ms=sum(fulltext_ms) / len(fulltext_ms) if fulltext_ms else 0.0,
        )


async def _sample_probe_vectors(connection: AsyncConnection, probes: int) -> list[str]:
    """Take existing embeddings as query vectors, returned in pgvector literal form."""

    result = await connection.execute(
        text(
            "SELECT embedding::text FROM chunks "
            "WHERE embedding IS NOT NULL ORDER BY random() LIMIT :limit"
        ),
        {"limit": probes},
    )
    return [row[0] for row in result]


async def _sample_probe_terms(connection: AsyncConnection, probes: int) -> list[str]:
    """Take the leading words of stored chunks as full-text query terms."""

    result = await connection.execute(
        text("SELECT substring(text from 1 for 12) FROM chunks ORDER BY random() LIMIT :limit"),
        {"limit": probes},
    )
    return [row[0] for row in result]


async def _measure(
    connection: AsyncConnection,
    probe_vectors: list[str],
    probe_terms: list[str],
    top_k: int,
) -> LatencyReport:
    """Time one vector query and one full-text query per probe."""

    vector_samples: list[float] = []
    for probe_vector in probe_vectors:
        start = time.perf_counter()
        await connection.execute(
            text(
                "SELECT id FROM chunks ORDER BY embedding <=> CAST(:probe AS vector) LIMIT :top_k"
            ),
            {"probe": probe_vector, "top_k": top_k},
        )
        vector_samples.append((time.perf_counter() - start) * 1000)

    fulltext_samples: list[float] = []
    for probe_term in probe_terms:
        start = time.perf_counter()
        await connection.execute(
            text(
                f"SELECT id FROM chunks "
                f"WHERE to_tsvector('{FULLTEXT_REGCONFIG}', text) "
                f"@@ plainto_tsquery('{FULLTEXT_REGCONFIG}', :probe) LIMIT :top_k"
            ),
            {"probe": probe_term, "top_k": top_k},
        )
        fulltext_samples.append((time.perf_counter() - start) * 1000)

    return LatencyReport.from_samples(vector_samples, fulltext_samples)


def _format_delta(before_ms: float, after_ms: float) -> str:
    """Render an after/before comparison as a speedup factor."""

    if after_ms <= 0:
        return "n/a"
    return f"{before_ms / after_ms:.2f}x"


async def rebuild_indexes(probes: int, top_k: int) -> None:
    """Benchmark without indexes, rebuild them with timing, benchmark again."""

    settings = get_settings()
    engine = create_async_engine(settings.database_url, hide_parameters=True)

    try:
        async with engine.begin() as connection:
            chunk_count = (
                await connection.execute(text("SELECT count(*) FROM chunks"))
            ).scalar_one()
            if chunk_count == 0:
                logger.warning("chunks table is empty; nothing worth indexing or measuring")
                return

            effective_fulltext_probes = min(probes, chunk_count)
            probe_vectors = await _sample_probe_vectors(connection, probes)
            probe_terms = await _sample_probe_terms(connection, effective_fulltext_probes)
            logger.info(
                "Starting index rebuild",
                chunk_count=chunk_count,
                vector_probes=len(probe_vectors),
                fulltext_probes=len(probe_terms),
            )

            await connection.execute(text("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw"))
            await connection.execute(text("DROP INDEX IF EXISTS ix_chunks_text_gin"))
            before = await _measure(connection, probe_vectors, probe_terms, top_k)
            logger.info(
                "Baseline measured without indexes",
                vector_mean_ms=round(before.vector_mean_ms, 3),
                fulltext_mean_ms=round(before.fulltext_mean_ms, 3),
            )

            start = time.perf_counter()
            await connection.execute(text(CREATE_HNSW))
            hnsw_seconds = time.perf_counter() - start
            logger.info("HNSW index built", duration_seconds=round(hnsw_seconds, 3))

            start = time.perf_counter()
            await connection.execute(text(CREATE_GIN))
            gin_seconds = time.perf_counter() - start
            logger.info("GIN index built", duration_seconds=round(gin_seconds, 3))

            # ANALYZE first: without fresh statistics the planner may keep choosing a
            # sequential scan and the "after" numbers would understate the indexes.
            await connection.execute(text("ANALYZE chunks"))
            after = await _measure(connection, probe_vectors, probe_terms, top_k)

        _print_report(
            chunk_count,
            len(probe_vectors),
            len(probe_terms),
            top_k,
            hnsw_seconds,
            gin_seconds,
            before,
            after,
        )
    finally:
        await engine.dispose()


def _print_report(
    chunk_count: int,
    vector_probes: int,
    fulltext_probes: int,
    top_k: int,
    hnsw_seconds: float,
    gin_seconds: float,
    before: LatencyReport,
    after: LatencyReport,
) -> None:
    """Print the Stage 3 baseline table."""

    rule = "=" * 66
    print(f"\n{rule}")
    print(
        f"  Index rebuild — {chunk_count} chunks, "
        f"{vector_probes} vector probes, {fulltext_probes} text probes, top_k={top_k}"
    )
    print(rule)
    print("  Build time")
    print(f"    HNSW (vector_cosine_ops)   {hnsw_seconds:8.3f}s")
    print(f"    GIN  (tsvector)            {gin_seconds:8.3f}s")
    print(f"    Total                      {hnsw_seconds + gin_seconds:8.3f}s")
    print("  Query latency (ms/query)        before     after    speedup")
    print(
        f"    Vector mean            {before.vector_mean_ms:10.3f}"
        f"{after.vector_mean_ms:10.3f}"
        f"{_format_delta(before.vector_mean_ms, after.vector_mean_ms):>11}"
    )
    print(
        f"    Vector p95             {before.vector_p95_ms:10.3f}"
        f"{after.vector_p95_ms:10.3f}"
        f"{_format_delta(before.vector_p95_ms, after.vector_p95_ms):>11}"
    )
    print(
        f"    Full-text mean         {before.fulltext_mean_ms:10.3f}"
        f"{after.fulltext_mean_ms:10.3f}"
        f"{_format_delta(before.fulltext_mean_ms, after.fulltext_mean_ms):>11}"
    )
    print(f"{rule}\n")
    print("  A speedup below 1x is not a bug. On a small table a sequential scan is")
    print("  already fast, and a full-text probe that matches most rows costs more")
    print("  through the index than through a scan that stops at LIMIT.\n")


def main() -> None:
    """Parse arguments and run the rebuild."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probes", type=int, default=DEFAULT_PROBES, help="query samples per phase"
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="rows each probe returns")
    arguments = parser.parse_args()

    asyncio.run(rebuild_indexes(probes=arguments.probes, top_k=arguments.top_k))


if __name__ == "__main__":
    main()
