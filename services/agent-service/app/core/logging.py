"""Structured logging configuration for the application"""

import structlog
from app.config import get_settings
from common.logging import configure_logging as configure_common_logging
from common.logging import get_logger

_configured = False


def configure_logging() -> structlog.BoundLogger:
    """
    Configure structured logging with JSON output

    Returns:
        Configured structlog logger instance

    Examples:
        >>> logger = configure_logging()
        >>> logger.info("event_name", key="value")
    """
    global _configured
    if _configured:
        logger: structlog.BoundLogger = get_logger(__name__)
        return logger

    settings = get_settings()

    configure_common_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)

    _configured = True

    logger = get_logger(__name__)

    return logger
