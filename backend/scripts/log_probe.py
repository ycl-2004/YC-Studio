"""Emit production JSON logs for the repeatable Step 7 acceptance check.

The probe routes exist only in this subprocess application instance and are
never registered on the production ``app.main:app`` object.
"""

import asyncio
import json
import logging

import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import engine
from app.main import create_app

logger = structlog.stdlib.get_logger(__name__)


def create_probe_app() -> FastAPI:
    """Create one app instance with temporary logging probe routes."""

    application = create_app()

    @application.get("/__step7/probe/{marker}")
    async def logging_probe(marker: str) -> dict[str, str]:
        structlog.contextvars.bind_contextvars(probe_marker=marker)
        logger.info("probe.application")
        logging.getLogger("uvicorn.error").info("probe.uvicorn_inside_request")
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"marker": marker}

    @application.get("/__step7/error")
    async def error_probe() -> None:
        structlog.contextvars.bind_contextvars(probe_marker="error")
        logger.info("probe.before_error")
        raise RuntimeError("intentional Step 7 logging probe failure")

    return application


async def main() -> None:
    """Exercise normal, concurrent, foreign-logger, SQL, and failure paths."""

    application = create_probe_app()
    transport = ASGITransport(app=application, raise_app_exceptions=False)

    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            alpha_response, beta_response = await asyncio.gather(
                client.get("/__step7/probe/alpha"),
                client.get("/__step7/probe/beta"),
            )
            error_response = await client.get("/__step7/error")

    logging.getLogger("uvicorn.error").info("probe.uvicorn_outside_request")
    print(
        json.dumps(
            {
                "event": "probe.summary",
                "normal_responses": [
                    {
                        "marker": response.json()["marker"],
                        "request_id": response.headers["X-Request-ID"],
                        "status_code": response.status_code,
                    }
                    for response in (alpha_response, beta_response)
                ],
                "error_status_code": error_response.status_code,
                "error_request_id": error_response.headers["X-Request-ID"],
                "error_body_request_id": error_response.json()["request_id"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
