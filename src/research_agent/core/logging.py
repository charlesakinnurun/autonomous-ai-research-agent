"""Structured logging.

Logs are JSON in production and human-readable in local development. Every log
call can bind ``run_id``/``trace_id``/``node`` without passing a logger around.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog


def configure_logging(level: str = "INFO", *, json_logs: bool | None = None) -> None:
    """Configure structlog + stdlib logging once at process startup."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric_level)

    if json_logs is None:
        json_logs = level.upper() != "DEBUG"

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "research_agent") -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def bind_run_context(*, run_id: str, trace_id: str) -> None:
    """Bind run identifiers to the current async context."""
    structlog.contextvars.bind_contextvars(run_id=run_id, trace_id=trace_id)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
