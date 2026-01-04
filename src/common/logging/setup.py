"""Structured logging setup compatible with log aggregation services.

This module configures structlog for JSON logging output that is compatible with:
- Datadog
- Splunk
- ELK Stack (Elasticsearch, Logstash, Kibana)
- AWS CloudWatch
- Google Cloud Logging
- Azure Monitor
- Grafana Loki
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from src.config import Settings


def add_app_context(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add application context to all log entries."""
    from src.config import get_settings

    settings = get_settings()
    event_dict["service"] = settings.app_name.lower().replace(" ", "-")
    event_dict["version"] = settings.app_version
    event_dict["environment"] = settings.environment
    return event_dict


def setup_logging(settings: Settings) -> None:
    """Configure structured logging based on settings.

    Args:
        settings: Application settings containing log configuration.
    """
    # Shared processors for all configurations
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_app_context,
    ]

    if settings.log_format == "json":
        # JSON format for production - compatible with log aggregation services
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console format for development - human readable
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A bound logger instance with structured logging capabilities.
    """
    return structlog.get_logger(name)
