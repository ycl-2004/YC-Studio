"""Unified structlog and standard-library logging configuration.

References:
- https://www.structlog.org/en/stable/contextvars.html
- https://www.structlog.org/en/stable/standard-library.html
- https://docs.sqlalchemy.org/en/20/core/engines.html#configuring-logging
"""

import logging
import sys
from typing import Literal

import structlog
from structlog.typing import Processor

Environment = Literal["development", "test", "production"]


def _shared_processors() -> list[Processor]:
    """Build processors shared by structlog and foreign stdlib records."""

    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]


def _replace_handlers(logger: logging.Logger) -> None:
    """Remove handlers installed before the application logging policy."""

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def configure_logging(environment: Environment) -> None:
    """Configure one renderer for application, Uvicorn, and SQLAlchemy logs."""

    shared_processors = _shared_processors()
    renderer: Processor
    if environment == "development":
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    else:
        renderer = structlog.processors.JSONRenderer(sort_keys=True)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    _replace_handlers(root_logger)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy"):
        foreign_logger = logging.getLogger(logger_name)
        _replace_handlers(foreign_logger)
        foreign_logger.propagate = True

    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.captureWarnings(True)
