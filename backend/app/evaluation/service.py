"""Dataset management, retrieval execution, attribution, and run comparison."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from time import perf_counter
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models.chunk import Chunk
from app.db.models.collection import Collection, CollectionKind, CollectionScope
from app.db.models.document import Document
from app.db.models.evaluation import EvalCase, EvalDataset, EvalResult, EvalRun
from app.db.models.source import Source
from app.evaluation.generation import (
    GeneratedQuestion,
    SyntheticQuestionGenerator,
    validate_generated_question,
)
from app.evaluation.metrics import RetrievalMetrics, evaluate_retrieval, percentile, weighted_mean
from app.rag.retriever.embeddings import get_local_embedding


class EvalCaseSource(str):
    """Stable source values stored in JSON/API responses."""

    SYNTHETIC = "synthetic"
    MANUAL = "manual"


class EvalRunStatus(str):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AttributionLabel(str):
    NOT_IN_KB = "not_in_kb"
    NOT_RECALLED = "not_recalled"
    LOW_RANK = "low_rank"
    HIT = "hit"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class EvaluationHit:
    """Minimal retrieval result needed by the evaluator, independent of HTTP schemas."""

    chunk_id: UUID
    document_id: UUID
    score: float


@dataclass(frozen=True, slots=True)
class DatasetStats:
    total: int
    active: int
    synthetic_total: int
    synthetic_active: int
    manual_active: int

    @property
    def synthetic_retention_rate(self) -> float:
        """Return active synthetic cases as a percentage of generated synthetic cases."""

        if self.synthetic_total == 0:
            return 0.0
        return self.synthetic_active / self.synthetic_total * 100.0


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """In-memory result used to build the immutable ORM row and run summary."""

    case_id: UUID
    source: str
    metrics: RetrievalMetrics
    attribution: str
    latency_ms: float
    error_message: str | None


Retriever = Callable[[str, int], Awaitable[list[EvaluationHit]]]


async def create_dataset(
    session: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    version_name: str,
    construction_method: str,
) -> EvalDataset:
    """Create an owned, versioned dataset shell."""

    dataset = EvalDataset(
        user_id=user_id,
        name=name,
        version=version_name,
        construction_method=construction_method,
        case_count=0,
    )
    session.add(dataset)
    await session.flush()
    return dataset


async def refresh_dataset_case_count(session: AsyncSession, dataset_id: UUID) -> DatasetStats:
    """Recompute cached active count and return all Step 3 quality numbers."""

    rows = await session.execute(
        select(EvalCase.source, EvalCase.is_active, func.count())
        .where(EvalCase.dataset_id == dataset_id)
        .group_by(EvalCase.source, EvalCase.is_active)
    )
    counts = {(str(source), bool(active)): int(count) for source, active, count in rows}
    total = sum(counts.values())
    active = sum(count for (source, is_active), count in counts.items() if is_active)
    synthetic_total = sum(
        count for (source, _), count in counts.items() if source == EvalCaseSource.SYNTHETIC
    )
    synthetic_active = counts.get((EvalCaseSource.SYNTHETIC, True), 0)
    manual_active = counts.get((EvalCaseSource.MANUAL, True), 0)
    dataset = await session.get(EvalDataset, dataset_id)
    if dataset is not None:
        dataset.case_count = active
    return DatasetStats(total, active, synthetic_total, synthetic_active, manual_active)


async def add_manual_cases(
    session: AsyncSession,
    *,
    dataset_id: UUID,
    cases: Sequence[tuple[str, Sequence[UUID], str | None]],
) -> list[EvalCase]:
    """Add human-confirmed queries and their manually selected relevant chunks."""

    created: list[EvalCase] = []
    for query, expected_chunk_ids, review_note in cases:
        normalized_query = " ".join(query.split())
        expected = [str(chunk_id) for chunk_id in expected_chunk_ids]
        if not normalized_query:
            raise ValueError("manual evaluation query cannot be empty")
        if not expected:
            raise ValueError("manual evaluation case needs at least one expected chunk")
        created.append(
            EvalCase(
                dataset_id=dataset_id,
                query=normalized_query,
                expected_chunk_ids=expected,
                source=EvalCaseSource.MANUAL,
                is_active=True,
                review_note=review_note or "human-confirmed expected chunks",
            )
        )
    session.add_all(created)
    await session.flush()
    await refresh_dataset_case_count(session, dataset_id)
    return created


async def generate_synthetic_cases(
    session: AsyncSession,
    *,
    dataset_id: UUID,
    count: int,
    generator: SyntheticQuestionGenerator,
    seed: int = 0,
) -> list[EvalCase]:
    """Sample distinct searchable chunks and persist validated synthetic cases."""

    if count < 1:
        raise ValueError("synthetic case count must be positive")
    dataset = await session.get(EvalDataset, dataset_id)
    if dataset is None:
        raise LookupError(f"Evaluation dataset {dataset_id} was not found")
    chunks = list(
        (
            await session.scalars(
                select(Chunk)
                .join(Document, Chunk.document_id == Document.id)
                .join(Source, Document.source_id == Source.id)
                .join(Collection, Chunk.collection_id == Collection.id)
                .where(
                    Collection.kind.in_((CollectionKind.CASE, CollectionKind.MATERIAL)),
                    or_(
                        Collection.scope == CollectionScope.PUBLIC,
                        Collection.user_id == dataset.user_id,
                    ),
                    Chunk.embedding.is_not(None),
                    Document.deleted_at.is_(None),
                    Source.deleted_at.is_(None),
                )
                .order_by(Chunk.id)
            )
        ).all()
    )
    # The deterministic shuffle makes the chosen chunk ids reproducible without using
    # PostgreSQL random(), which would make a run impossible to explain later.
    import random

    random.Random(seed).shuffle(chunks)
    if len(chunks) < count:
        raise ValueError(f"only {len(chunks)} eligible public searchable chunks; need {count}")

    created: list[EvalCase] = []
    for chunk in chunks[:count]:
        question: GeneratedQuestion = validate_generated_question(
            await generator.generate(chunk.text)
        )
        created.append(
            EvalCase(
                dataset_id=dataset_id,
                query=question.query,
                expected_chunk_ids=[str(chunk.id)],
                source=EvalCaseSource.SYNTHETIC,
                is_active=True,
                review_note="pending human review",
                case_metadata={"generator_rationale": question.rationale, "seed": seed},
            )
        )
    session.add_all(created)
    await session.flush()
    await refresh_dataset_case_count(session, dataset_id)
    return created


async def review_case(
    session: AsyncSession,
    *,
    case_id: UUID,
    is_active: bool,
    review_note: str | None,
) -> EvalCase:
    """Keep the case row for audit while allowing human filtering to deactivate it."""

    case = await session.get(EvalCase, case_id)
    if case is None:
        raise LookupError(f"Evaluation case {case_id} was not found")
    case.is_active = is_active
    case.review_note = review_note
    await refresh_dataset_case_count(session, case.dataset_id)
    return case


def default_config_snapshot(settings: Settings | None = None) -> dict[str, object]:
    """Freeze all retrieval inputs that affect a baseline comparison."""

    settings = settings or get_settings()
    try:
        runtime_version = f"sentence-transformers=={version('sentence-transformers')}"
    except PackageNotFoundError:
        runtime_version = "sentence-transformers==unknown"
    return {
        "retrieval_strategy": "vector",
        "top_k": settings.retrieval_top_k,
        "fusion": "none",
        "rerank": False,
        "embedding_model": settings.embedding_model,
        "embedding_version": runtime_version,
        "chunk": {
            "size": settings.chunk_size,
            "overlap": settings.chunk_overlap,
            "method": settings.chunk_method,
        },
        "temperature": 0.0,
        "seed": 0,
        "max_concurrency": 1,
        "evaluator_version": "stage2.v1",
        "source_weights": {EvalCaseSource.SYNTHETIC: 1.0, EvalCaseSource.MANUAL: 2.0},
    }


def merge_config_snapshot(
    base: dict[str, object],
    overrides: dict[str, object] | None,
) -> dict[str, object]:
    """Merge explicit top-level overrides while keeping the base fully serializable."""

    snapshot = dict(base)
    if overrides:
        snapshot.update(overrides)
    return snapshot


async def create_eval_run(
    session: AsyncSession,
    *,
    user_id: UUID,
    dataset_id: UUID,
    config_overrides: dict[str, object] | None = None,
) -> EvalRun:
    """Create a queued run with an immutable configuration snapshot."""

    dataset = await session.get(EvalDataset, dataset_id)
    if dataset is None:
        raise LookupError(f"Evaluation dataset {dataset_id} was not found")
    if dataset.user_id != user_id:
        raise PermissionError("Only the dataset owner may run an evaluation")
    await refresh_dataset_case_count(session, dataset_id)
    snapshot = merge_config_snapshot(default_config_snapshot(), config_overrides)
    snapshot.update({"dataset_id": str(dataset.id), "dataset_version": dataset.version})
    run = EvalRun(
        dataset_id=dataset.id,
        user_id=user_id,
        status=EvalRunStatus.QUEUED,
        config_snapshot=snapshot,
    )
    session.add(run)
    await session.flush()
    return run


async def retrieve_for_evaluation(
    session: AsyncSession,
    *,
    user_id: UUID,
    query: str,
    top_k: int,
) -> list[EvaluationHit]:
    """Run the Stage 2 vector baseline over both case and material libraries."""

    query_vector = get_local_embedding().embed_query(query)
    distance = Chunk.embedding.cosine_distance(query_vector).label("cosine_distance")
    statement = (
        select(Chunk.id, Document.id, distance)
        .join(Document, Chunk.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .join(Collection, Chunk.collection_id == Collection.id)
        .where(
            Chunk.embedding.is_not(None),
            Collection.kind.in_((CollectionKind.CASE, CollectionKind.MATERIAL)),
            Document.deleted_at.is_(None),
            Source.deleted_at.is_(None),
            or_(Collection.scope == CollectionScope.PUBLIC, Collection.user_id == user_id),
        )
        .order_by(distance, Chunk.id)
        .limit(top_k)
    )
    rows = (await session.execute(statement)).all()
    return [
        EvaluationHit(
            chunk_id=chunk_id,
            document_id=document_id,
            score=_score(distance_value),
        )
        for chunk_id, document_id, distance_value in rows
    ]


async def visible_searchable_chunk_ids(session: AsyncSession, *, user_id: UUID) -> set[str]:
    """Load the knowledge-base membership set used to distinguish missing knowledge."""

    statement = (
        select(Chunk.id)
        .join(Document, Chunk.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .join(Collection, Chunk.collection_id == Collection.id)
        .where(
            Chunk.embedding.is_not(None),
            Collection.kind.in_((CollectionKind.CASE, CollectionKind.MATERIAL)),
            Document.deleted_at.is_(None),
            Source.deleted_at.is_(None),
            or_(Collection.scope == CollectionScope.PUBLIC, Collection.user_id == user_id),
        )
    )
    return {str(chunk_id) for chunk_id in await session.scalars(statement)}


def _score(cosine_distance: float) -> float:
    return min(1.0, max(0.0, 1.0 - float(cosine_distance) / 2.0))


def classify_attribution(
    *,
    expected_ids: Sequence[str],
    retrieved: Sequence[EvaluationHit],
    known_chunk_ids: set[str],
) -> str:
    """Classify failure at the layer that can actually fix it."""

    expected = {str(chunk_id) for chunk_id in expected_ids}
    if not expected.intersection(known_chunk_ids):
        return AttributionLabel.NOT_IN_KB
    hit_indexes = [
        index
        for index, item in enumerate(retrieved, start=1)
        if str(item.chunk_id) in expected
    ]
    if not hit_indexes:
        return AttributionLabel.NOT_RECALLED
    if len({item.document_id for item in retrieved[:3]}) > 1 and len(retrieved) >= 2:
        top_scores = [item.score for item in retrieved[:3]]
        if max(top_scores) - min(top_scores) <= 0.03:
            return AttributionLabel.AMBIGUOUS
    if min(hit_indexes) > 3:
        return AttributionLabel.LOW_RANK
    return AttributionLabel.HIT


def _source_weight(config: dict[str, object], source: str) -> float:
    weights = config.get("source_weights", {})
    if isinstance(weights, dict):
        value = weights.get(source, 1.0)
        return float(value) if isinstance(value, (int, float)) else 1.0
    return 1.0


def summarize_outcomes(
    outcomes: Sequence[CaseOutcome],
    config: dict[str, object],
) -> dict[str, object]:
    """Aggregate metrics, latency and attribution percentages for the run record."""

    weights = [_source_weight(config, outcome.source) for outcome in outcomes]
    metrics: dict[str, object] = {
        "case_count": len(outcomes),
        "completed_cases": sum(outcome.error_message is None for outcome in outcomes),
        "failed_cases": sum(outcome.error_message is not None for outcome in outcomes),
        "recall_at_k": weighted_mean([outcome.metrics.recall for outcome in outcomes], weights),
        "mrr": weighted_mean([outcome.metrics.mrr for outcome in outcomes], weights),
        "ndcg_at_k": weighted_mean([outcome.metrics.ndcg for outcome in outcomes], weights),
        "latency_p50_ms": percentile([outcome.latency_ms for outcome in outcomes], 50),
        "latency_p95_ms": percentile([outcome.latency_ms for outcome in outcomes], 95),
    }
    attribution_counts = {
        label: sum(outcome.attribution == label for outcome in outcomes)
        for label in (
            AttributionLabel.NOT_IN_KB,
            AttributionLabel.NOT_RECALLED,
            AttributionLabel.LOW_RANK,
            AttributionLabel.HIT,
            AttributionLabel.AMBIGUOUS,
        )
    }
    denominator = len(outcomes) or 1
    metrics["attribution_counts"] = attribution_counts
    metrics["attribution_percentages"] = {
        label: count / denominator * 100 for label, count in attribution_counts.items()
    }
    return metrics


async def run_evaluation(
    session: AsyncSession,
    *,
    run_id: UUID,
    retriever: Retriever | None = None,
) -> dict[str, object]:
    """Execute every active case; one retrieval failure becomes one result row."""

    run = await session.get(EvalRun, run_id)
    if run is None:
        raise LookupError(f"Evaluation run {run_id} was not found")
    run.status = EvalRunStatus.RUNNING
    run.started_at = datetime.now(UTC)
    await session.commit()

    config = run.config_snapshot
    top_k_value = config.get("top_k", 5)
    top_k = int(top_k_value) if isinstance(top_k_value, (int, float, str)) else 5
    actual_retriever = retriever or (
        lambda query, limit: retrieve_for_evaluation(
            session,
            user_id=run.user_id,
            query=query,
            top_k=limit,
        )
    )
    cases = list(
        (
            await session.scalars(
                select(EvalCase)
                .where(EvalCase.dataset_id == run.dataset_id, EvalCase.is_active.is_(True))
                .order_by(EvalCase.created_at, EvalCase.id)
            )
        ).all()
    )
    known_chunk_ids = await visible_searchable_chunk_ids(session, user_id=run.user_id)
    outcomes: list[CaseOutcome] = []
    for case in cases:
        started = perf_counter()
        error_message: str | None = None
        try:
            retrieved = await actual_retriever(case.query, top_k)
        except Exception as error:  # a bad case must not erase the rest of the run
            retrieved = []
            error_message = f"{type(error).__name__}: {error}"
        elapsed_ms = (perf_counter() - started) * 1_000
        retrieved_ids = [item.chunk_id for item in retrieved]
        metrics = evaluate_retrieval(retrieved_ids, case.expected_chunk_ids, top_k)
        attribution = classify_attribution(
            expected_ids=case.expected_chunk_ids,
            retrieved=retrieved,
            known_chunk_ids=known_chunk_ids,
        )
        outcomes.append(
            CaseOutcome(
                case.id,
                case.source,
                metrics,
                attribution,
                elapsed_ms,
                error_message,
            )
        )
        session.add(
            EvalResult(
                run_id=run.id,
                case_id=case.id,
                retrieved_chunk_ids=[str(item.chunk_id) for item in retrieved],
                retrieved_document_ids=[str(item.document_id) for item in retrieved],
                retrieved_scores=[float(item.score) for item in retrieved],
                hit_positions=metrics.hit_positions,
                recall_at_k=metrics.recall,
                mrr=metrics.mrr,
                ndcg_at_k=metrics.ndcg,
                attribution=attribution,
                latency_ms=elapsed_ms,
                error_message=error_message,
            )
        )
    summary = summarize_outcomes(outcomes, config)
    run.status = EvalRunStatus.COMPLETED
    run.finished_at = datetime.now(UTC)
    run.summary_metrics = summary
    await session.commit()
    return summary


async def fail_evaluation_run(session: AsyncSession, *, run_id: UUID, message: str) -> None:
    """Persist a worker-level failure separately from per-case failures."""

    run = await session.get(EvalRun, run_id)
    if run is None:
        return
    run.status = EvalRunStatus.FAILED
    run.finished_at = datetime.now(UTC)
    run.error_message = message
    await session.commit()


async def list_runs(session: AsyncSession, *, user_id: UUID, limit: int = 50) -> list[EvalRun]:
    """List newest owned runs, including queued and failed runs."""

    return list(
        (
            await session.scalars(
                select(EvalRun)
                .where(EvalRun.user_id == user_id)
                .order_by(EvalRun.created_at.desc(), EvalRun.id.desc())
                .limit(limit)
            )
        ).all()
    )


async def compare_runs(
    session: AsyncSession,
    *,
    current_run_id: UUID,
    baseline_run_id: UUID,
    user_id: UUID,
) -> dict[str, object]:
    """Compare summaries, configs and every case that exists in both runs."""

    current = await session.get(EvalRun, current_run_id)
    baseline = await session.get(EvalRun, baseline_run_id)
    if current is None or baseline is None:
        raise LookupError("One of the evaluation runs was not found")
    if current.user_id != user_id or baseline.user_id != user_id:
        raise PermissionError("Only the run owner may compare evaluation runs")
    baseline_rows = {
        row.case_id: row
        for row in (
            await session.scalars(select(EvalResult).where(EvalResult.run_id == baseline.id))
        ).all()
    }
    current_rows = {
        row.case_id: row
        for row in (
            await session.scalars(select(EvalResult).where(EvalResult.run_id == current.id))
        ).all()
    }
    cases = {
        case.id: case
        for case in (
            await session.scalars(
                select(EvalCase).where(
                    EvalCase.id.in_(set(baseline_rows) | set(current_rows))
                )
            )
        ).all()
    }
    diffs: list[dict[str, object]] = []
    for case_id in sorted(set(baseline_rows) | set(current_rows), key=str):
        before = baseline_rows.get(case_id)
        after = current_rows.get(case_id)
        before_values = _result_values(before)
        after_values = _result_values(after)
        delta = {
            key: after_values[key] - before_values[key]
            for key in before_values
            if key in after_values
        }
        score_delta = sum(delta.values())
        state = "improved" if score_delta > 0 else "regressed" if score_delta < 0 else "unchanged"
        diffs.append(
            {
                "case_id": str(case_id),
                "query": cases[case_id].query if case_id in cases else "",
                "state": state,
                "baseline": before_values,
                "current": after_values,
                "delta": delta,
            }
        )
    return {
        "baseline_run_id": str(baseline.id),
        "current_run_id": str(current.id),
        "baseline_summary": baseline.summary_metrics or {},
        "current_summary": current.summary_metrics or {},
        "config_diff": _config_diff(baseline.config_snapshot, current.config_snapshot),
        "case_diffs": diffs,
        "improved_cases": [diff for diff in diffs if diff["state"] == "improved"],
        "regressed_cases": [diff for diff in diffs if diff["state"] == "regressed"],
    }


def _result_values(result: EvalResult | None) -> dict[str, float]:
    if result is None:
        return {"recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0}
    return {
        "recall_at_k": result.recall_at_k,
        "mrr": result.mrr,
        "ndcg_at_k": result.ndcg_at_k,
    }


def _config_diff(
    before: dict[str, object],
    after: dict[str, object],
) -> dict[str, dict[str, object]]:
    keys = set(before) | set(after)
    return {
        key: {"baseline": before.get(key), "current": after.get(key)}
        for key in sorted(keys)
        if before.get(key) != after.get(key)
    }
