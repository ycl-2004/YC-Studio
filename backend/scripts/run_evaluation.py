"""Run one Stage 2 evaluation locally and print its reproducible summary."""

import argparse
import asyncio
import json
from uuid import UUID

from app.db.session import async_session_factory
from app.evaluation.service import create_eval_run, run_evaluation


async def run(dataset_id: UUID, user_id: UUID, top_k: int) -> None:
    async with async_session_factory() as session:
        evaluation_run = await create_eval_run(
            session,
            user_id=user_id,
            dataset_id=dataset_id,
            config_overrides={"top_k": top_k},
        )
        await session.commit()
        summary = await run_evaluation(session, run_id=evaluation_run.id)
    print(json.dumps({"run_id": str(evaluation_run.id), "summary": summary}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", required=True, type=UUID)
    parser.add_argument("--user-id", required=True, type=UUID)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")
    asyncio.run(run(args.dataset_id, args.user_id, args.top_k))


if __name__ == "__main__":
    main()
