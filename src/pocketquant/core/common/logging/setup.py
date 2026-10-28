import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from pocketquant.core.config import Settings

# Context key bound around a backtest replay; see drop_backtest_info.
BACKTEST_RUN_ID = "backtest_run_id"


def add_correlation_id(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    from pocketquant.core.common.tracing.context import get_correlation_id

    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def add_app_context(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    from pocketquant.core.config import get_settings

    settings = get_settings()
    event_dict["service"] = settings.app_name.lower().replace(" ", "-")
    event_dict["version"] = settings.app_version
    event_dict["environment"] = settings.environment
    return event_dict


def drop_backtest_info(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Drop INFO lines logged inside a backtest replay.

    A replay reuses the live order and strategy services, so their per-fill INFO
    lines would reach the prod log mixed with live fills. Warnings and errors pass.
    """
    if method_name == "info" and BACKTEST_RUN_ID in event_dict:
        raise structlog.DropEvent
    return event_dict


def setup_logging(settings: Settings) -> None:
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        drop_backtest_info,  # type: ignore[list-item]
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_correlation_id,  # type: ignore[list-item]
        add_app_context,  # type: ignore[list-item]
    ]

    if settings.log_format == "json":
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(
                colors=True,
                # Tracebacks reach the public deploy output; locals can hold secrets.
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    # Its DEBUG handshake log prints the request headers, Exness API key included.
    logging.getLogger("websockets").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
