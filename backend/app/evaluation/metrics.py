"""Pure retrieval metrics used by production runs and fast unit tests."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import log2


def _as_strings(values: Iterable[object]) -> list[str]:
    return [str(value) for value in values]


def _relevant_positions(
    retrieved_ids: Sequence[object],
    expected_ids: Iterable[object],
    k: int,
) -> list[int]:
    expected = {str(value) for value in expected_ids}
    return [
        index
        for index, value in enumerate(_as_strings(retrieved_ids[:k]), start=1)
        if value in expected
    ]


def recall_at_k(
    retrieved_ids: Sequence[object],
    expected_ids: Sequence[object],
    k: int,
) -> float:
    """Return the fraction of relevant chunks found in the first ``k`` results."""

    expected = {str(value) for value in expected_ids}
    if not expected or k <= 0:
        return 0.0
    hit_count = len(expected.intersection(_as_strings(retrieved_ids[:k])))
    return min(1.0, max(0.0, hit_count / len(expected)))


def reciprocal_rank(
    retrieved_ids: Sequence[object],
    expected_ids: Sequence[object],
    k: int | None = None,
) -> float:
    """Return reciprocal rank of the first relevant result, or zero on a miss."""

    limit = len(retrieved_ids) if k is None else max(0, k)
    positions = _relevant_positions(retrieved_ids, expected_ids, limit)
    return 1.0 / positions[0] if positions else 0.0


def ndcg_at_k(
    retrieved_ids: Sequence[object],
    expected_ids: Sequence[object],
    k: int,
) -> float:
    """Return binary-relevance NDCG@k with the ideal ranking as denominator."""

    expected = {str(value) for value in expected_ids}
    if not expected or k <= 0:
        return 0.0
    positions = _relevant_positions(retrieved_ids, expected, k)
    dcg = sum(1.0 / log2(position + 1) for position in positions)
    ideal_hits = min(len(expected), k)
    idcg = sum(1.0 / log2(position + 1) for position in range(1, ideal_hits + 1))
    return min(1.0, max(0.0, dcg / idcg)) if idcg else 0.0


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    """The three per-case metrics plus one-based hit positions."""

    recall: float
    mrr: float
    ndcg: float
    hit_positions: list[int]


def evaluate_retrieval(
    retrieved_ids: Sequence[object],
    expected_ids: Sequence[object],
    k: int,
) -> RetrievalMetrics:
    """Compute all metrics once so result rows cannot disagree about the cutoff."""

    return RetrievalMetrics(
        recall=recall_at_k(retrieved_ids, expected_ids, k),
        mrr=reciprocal_rank(retrieved_ids, expected_ids, k),
        ndcg=ndcg_at_k(retrieved_ids, expected_ids, k),
        hit_positions=_relevant_positions(retrieved_ids, expected_ids, k),
    )


def weighted_mean(values: Sequence[float], weights: Sequence[float] | None = None) -> float:
    """Return a bounded weighted mean; manual cases can therefore carry more weight."""

    if not values:
        return 0.0
    if weights is None:
        return sum(values) / len(values)
    if len(values) != len(weights) or not any(weights):
        return 0.0
    return sum(value * weight for value, weight in zip(values, weights, strict=True)) / sum(weights)


def percentile(values: Sequence[float], percentile_value: float) -> float:
    """Return a nearest-rank percentile without a statistics dependency."""

    if not values:
        return 0.0
    if not 0 <= percentile_value <= 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(values)
    rank = max(1, int((percentile_value / 100) * len(ordered) + 0.999999))
    return ordered[min(len(ordered), rank) - 1]
