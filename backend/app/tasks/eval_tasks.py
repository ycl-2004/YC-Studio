"""ARQ jobs for synthetic dataset generation and retrieval evaluation."""

from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.evaluation.generation import (
    DeterministicQuestionGenerator,
    HttpJsonQuestionGenerator,
    SyntheticQuestionGenerator,
)
from app.evaluation.service import (
    fail_evaluation_run,
    generate_synthetic_cases,
    run_evaluation,
)


async def generate_eval_dataset(
    ctx: dict[str, Any],
    dataset_id: str,
    count: int,
    seed: int,
    mode: str = "http",
) -> dict[str, str | int]:
    """Generate cases in the worker so an LLM call never blocks an HTTP request."""

    del ctx
    settings = get_settings()
    if mode == "offline":
        generator: SyntheticQuestionGenerator = DeterministicQuestionGenerator()
    else:
        generator = HttpJsonQuestionGenerator(
            endpoint=f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.0,
        )
    async with async_session_factory() as session:
        cases = await generate_synthetic_cases(
            session,
            dataset_id=UUID(dataset_id),
            count=count,
            generator=generator,
            seed=seed,
        )
        await session.commit()
    return {"dataset_id": dataset_id, "status": "completed", "count": len(cases)}


async def evaluate_run(ctx: dict[str, Any], run_id: str) -> dict[str, object]:
    """Run one durable evaluation and keep worker-level failures in the run row."""

    del ctx
    parsed_run_id = UUID(run_id)
    async with async_session_factory() as session:
        try:
            summary = await run_evaluation(session, run_id=parsed_run_id)
        except Exception as error:
            await session.rollback()
            await fail_evaluation_run(
                session,
                run_id=parsed_run_id,
                message=f"{type(error).__name__}: {error}"[:1_000],
            )
            raise
    return summary
