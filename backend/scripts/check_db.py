"""Repeatable Stage 0 Step 4 verification against the development database."""

import asyncio
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory, engine, get_session

PROBE_TABLE = "stage0_step4_probe"
probe_app = FastAPI()


@probe_app.get("/select-one")
async def select_one(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, int]:
    value = await session.scalar(text("SELECT 1"))

    assert value is not None
    return {"value": value}


@probe_app.get("/concurrent/{worker_id}")
async def concurrent_query(
    worker_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, int]:
    value = await session.scalar(
        text("SELECT CAST(:worker_id AS INTEGER) FROM pg_sleep(0.05)"),
        {"worker_id": worker_id},
    )

    assert value is not None
    return {"worker_id": value}


@probe_app.post("/commit")
async def commit_row(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    await session.execute(
        text(f'INSERT INTO "{PROBE_TABLE}" (id, note) VALUES (1, :note)'),
        {"note": "explicit commit"},
    )
    await session.commit()
    return {"status": "committed"}


@probe_app.post("/rollback/{row_id}")
async def roll_back_row(
    row_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await session.execute(
        text(f'INSERT INTO "{PROBE_TABLE}" (id, note) VALUES (:id, :note)'),
        {"id": row_id, "note": "must roll back"},
    )
    raise HTTPException(status_code=500, detail="intentional rollback probe")


def create_probe_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=probe_app), base_url="http://step4.test")


async def check_select_one() -> None:
    async with create_probe_client() as client:
        response = await client.get("/select-one")

    assert response.status_code == 200
    assert response.json() == {"value": 1}
    print("[1/4] temporary route SELECT 1: ok")


async def check_concurrency() -> None:
    async with create_probe_client() as client:
        responses = await asyncio.gather(
            *(client.get(f"/concurrent/{worker_id}") for worker_id in range(10))
        )

    assert all(response.status_code == 200 for response in responses)
    assert [response.json()["worker_id"] for response in responses] == list(range(10))
    print("[2/4] 10 concurrent requests with independent sessions: ok")


async def create_probe_table() -> None:
    async with engine.begin() as connection:
        await connection.execute(text(f'DROP TABLE IF EXISTS "{PROBE_TABLE}"'))
        await connection.execute(
            text(f'CREATE TABLE "{PROBE_TABLE}" (id INTEGER PRIMARY KEY, note TEXT NOT NULL)')
        )


async def check_explicit_commit() -> None:
    async with create_probe_client() as client:
        response = await client.post("/commit")

    assert response.status_code == 200
    assert response.json() == {"status": "committed"}

    async with async_session_factory() as session:
        count = await session.scalar(text(f'SELECT COUNT(*) FROM "{PROBE_TABLE}"'))

    assert count == 1
    print("[3/4] service-level explicit commit persists: ok")


async def check_rollback_and_pool_reuse() -> None:
    async with create_probe_client() as client:
        for row_id in range(100, 150):
            response = await client.post(f"/rollback/{row_id}")
            assert response.status_code == 500

    async with async_session_factory() as session:
        count = await session.scalar(text(f'SELECT COUNT(*) FROM "{PROBE_TABLE}"'))
        value = await session.scalar(text("SELECT 1"))

    assert count == 1
    assert value == 1
    print("[4/4] 50 failures rolled back; connections remained reusable: ok")


async def drop_probe_table() -> None:
    async with engine.begin() as connection:
        await connection.execute(text(f'DROP TABLE IF EXISTS "{PROBE_TABLE}"'))


async def main() -> None:
    probe_table_created = False

    try:
        await check_select_one()
        await check_concurrency()
        await create_probe_table()
        probe_table_created = True
        await check_explicit_commit()
        await check_rollback_and_pool_reuse()
    finally:
        if probe_table_created:
            await drop_probe_table()
        await engine.dispose()

    print("Stage 0 Step 4 database checks passed; probe table removed.")


if __name__ == "__main__":
    asyncio.run(main())
