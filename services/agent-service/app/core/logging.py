"""Structured logging configuration for the application"""

import structlog
import logging
from app.config import get_settings


def configure_logging() -> structlog.BoundLogger:
    """
    Configure structured logging with JSON output
    
    Returns:
        Configured structlog logger instance
        
    Examples:
        >>> logger = configure_logging()
        >>> logger.info("event_name", key="value")
    """
    settings = get_settings()
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.LOG_LEVEL),
    )
    
    # Configure structlog processors
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    return structlog.get_logger()
