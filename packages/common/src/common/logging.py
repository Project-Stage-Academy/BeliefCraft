"""
Structured JSON logging configuration for all services.

Usage:
    from common.logging import configure_logging, get_logger

    # In main.py (once at startup)
    configure_logging("agent-service", log_level="INFO")

    # In any module
    logger = get_logger(__name__)
    logger.info("processing_started", user_id=123)
"""

import logging
import sys
from typing import Any, cast

import structlog
from structlog.types import EventDict, Processor

_configured = False  # Track if already configured


def configure_logging(service_name: str, log_level: str = "INFO") -> None:
    """
    Configure structured JSON logging for a service.

    This function modifies global logging state and should be called
    once at application startup. It is idempotent - multiple calls
    will not duplicate configuration.

    Args:
        service_name: Name of the service (e.g., "agent-service")
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Features:
        - JSON output for all logs
        - Automatic trace_id propagation via contextvars
        - Stack traces for errors
        - ISO timestamps
        - Service name in every log entry
    """
    global _configured
    if _configured:
        return

    level = getattr(logging, log_level.upper(), logging.INFO)

    def add_service_name(
        _logger: Any,
        _method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        event_dict["service"] = service_name
        return event_dict

    shared_processors: list[Processor] = [
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        add_service_name,
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.dict_tracebacks,
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=shared_processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger()

    # Safe handler removal (create copy before iteration)
    handlers_copy = root_logger.handlers[:]
    for h in handlers_copy:
        root_logger.removeHandler(h)

    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Configure uvicorn loggers
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(logger_name)
        log.handlers = [handler]
        log.propagate = False

    _configured = True


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """
    Get a structured logger for a module.

    Args:
        name: Module name (typically __name__). Optional.

    Returns:
        structlog BoundLogger instance

    Example:
        logger = get_logger(__name__)
        logger.info("user_action", user_id=123, action="login")
    """
    return cast(structlog.BoundLogger, structlog.get_logger(name))
