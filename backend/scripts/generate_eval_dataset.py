"""Generate Stage 2 synthetic cases from searchable case/material chunks."""

import argparse
import asyncio
import json
from uuid import UUID

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.evaluation.generation import (
    DeterministicQuestionGenerator,
    HttpJsonQuestionGenerator,
)
from app.evaluation.service import generate_synthetic_cases


async def generate(dataset_id: UUID, count: int, seed: int, mode: str) -> int:
    settings = get_settings()
    generator = (
        DeterministicQuestionGenerator()
        if mode == "offline"
        else HttpJsonQuestionGenerator(
            endpoint=f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.0,
        )
    )
    async with async_session_factory() as session:
        cases = await generate_synthetic_cases(
            session,
            dataset_id=dataset_id,
            count=count,
            generator=generator,
            seed=seed,
        )
        await session.commit()
    print(json.dumps({"dataset_id": str(dataset_id), "created": len(cases), "seed": seed}))
    return len(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", required=True, type=UUID)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mode", choices=("http", "offline"), default="http")
    args = parser.parse_args()
    if not 1 <= args.count <= 80:
        parser.error("--count must be between 1 and 80")
    asyncio.run(generate(args.dataset_id, args.count, args.seed, args.mode))


if __name__ == "__main__":
    main()
