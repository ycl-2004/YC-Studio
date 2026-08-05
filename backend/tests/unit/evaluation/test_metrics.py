"""Known-answer tests for Recall@k, MRR, and NDCG@k."""

from math import isclose, log2

from app.evaluation.metrics import (
    evaluate_retrieval,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_all_relevant_results_at_rank_one_are_perfect() -> None:
    metrics = evaluate_retrieval(["a", "b", "c"], ["a"], 5)

    assert metrics.recall == 1.0
    assert metrics.mrr == 1.0
    assert metrics.ndcg == 1.0
    assert metrics.hit_positions == [1]


def test_no_relevant_result_is_zero_for_all_metrics() -> None:
    metrics = evaluate_retrieval(["x", "y", "z"], ["a"], 5)

    assert metrics.recall == 0.0
    assert metrics.mrr == 0.0
    assert metrics.ndcg == 0.0
    assert metrics.hit_positions == []


def test_rank_three_has_the_expected_mrr_and_ndcg() -> None:
    assert reciprocal_rank(["x", "y", "a"], ["a"], 5) == 1 / 3
    assert isclose(ndcg_at_k(["x", "y", "a"], ["a"], 5), 1 / log2(4))
    assert recall_at_k(["x", "y", "a"], ["a"], 5) == 1.0


def test_recall_uses_the_relevant_set_as_denominator_and_is_bounded() -> None:
    assert recall_at_k(["a", "a", "b"], ["a", "b", "c"], 5) == 2 / 3
    assert 0.0 <= recall_at_k(["a", "b", "c", "d"], ["a"], 5) <= 1.0
