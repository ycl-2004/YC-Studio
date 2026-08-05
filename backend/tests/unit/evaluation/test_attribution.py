"""Pure attribution tests for the five Stage 2 failure classes."""

from uuid import UUID

from app.evaluation.service import AttributionLabel, EvaluationHit, classify_attribution

KNOWN = {"00000000-0000-0000-0000-000000000001"}
EXPECTED = "00000000-0000-0000-0000-000000000001"


def hit(chunk_id: str, document_id: str, score: float) -> EvaluationHit:
    return EvaluationHit(UUID(chunk_id), UUID(document_id), score)


def test_not_in_kb() -> None:
    assert (
        classify_attribution(expected_ids=["missing"], retrieved=[], known_chunk_ids=KNOWN)
        == AttributionLabel.NOT_IN_KB
    )


def test_not_recalled() -> None:
    assert (
        classify_attribution(
            expected_ids=[EXPECTED],
            retrieved=[
                hit(
                    "00000000-0000-0000-0000-000000000002",
                    "00000000-0000-0000-0000-000000000010",
                    0.9,
                )
            ],
            known_chunk_ids=KNOWN,
        )
        == AttributionLabel.NOT_RECALLED
    )


def test_low_rank_and_hit() -> None:
    distractors = [
        hit(
            f"00000000-0000-0000-0000-00000000000{i}",
            "00000000-0000-0000-0000-000000000010",
            0.9 - i / 100,
        )
        for i in range(2, 5)
    ]
    expected_hit = hit(EXPECTED, "00000000-0000-0000-0000-000000000010", 0.7)
    assert (
        classify_attribution(
            expected_ids=[EXPECTED],
            retrieved=distractors + [expected_hit],
            known_chunk_ids=KNOWN,
        )
        == AttributionLabel.LOW_RANK
    )
    assert (
        classify_attribution(
            expected_ids=[EXPECTED],
            retrieved=[expected_hit],
            known_chunk_ids=KNOWN,
        )
        == AttributionLabel.HIT
    )


def test_ambiguous_similarly_scored_hits_from_different_documents() -> None:
    first = hit(EXPECTED, "00000000-0000-0000-0000-000000000010", 0.900)
    second = hit(
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000011",
        0.885,
    )

    assert (
        classify_attribution(
            expected_ids=[EXPECTED],
            retrieved=[first, second],
            known_chunk_ids=KNOWN,
        )
        == AttributionLabel.AMBIGUOUS
    )
