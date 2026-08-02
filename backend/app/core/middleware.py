"""HTTP request context and access logging middleware.

References:
- https://www.structlog.org/en/stable/contextvars.html
- https://fastapi.tiangolo.com/tutorial/middleware/
"""

from time import perf_counter
from uuid import uuid4

import structlog
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"

logger = structlog.stdlib.get_logger(__name__)


class RequestContextMiddleware:
    """Bind an isolated request ID and emit one canonical completion event."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        request_id = str(uuid4())
        method = scope["method"]
        path = scope["path"]
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            http_method=method,
            http_path=path,
        )

        started_at = perf_counter()
        status_code = 500
        logger.info("request.started")

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception(
                "request.failed",
                status_code=500,
                duration_ms=_duration_ms(started_at),
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal Server Error",
                    "request_id": request_id,
                },
            )
            await response(scope, receive, send_with_request_id)
        else:
            log_method = logger.error if status_code >= 500 else logger.info
            log_method(
                "request.completed",
                status_code=status_code,
                duration_ms=_duration_ms(started_at),
            )
        finally:
            structlog.contextvars.clear_contextvars()


def _duration_ms(started_at: float) -> float:
    """Return elapsed monotonic time in milliseconds."""

    return round((perf_counter() - started_at) * 1000, 3)
