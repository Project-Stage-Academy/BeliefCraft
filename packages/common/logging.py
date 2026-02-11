"""
Structured JSON logging configuration for all services.

Usage:
    from common.logging import configure_logging, get_logger
    
    # In main.py
    configure_logging("agent-service", log_level="INFO")
    
    # In any module
    logger = get_logger(__name__)
    logger.info("processing_started", user_id=123, query="reorder?")
"""

import logging
import sys
import structlog
from typing import Any


def configure_logging(service_name: str, log_level: str = "INFO") -> None:
    """
    Configure structured JSON logging for a service.
    
    Args:
        service_name: Name of the service (e.g., "agent-service", "rag-service")
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Features:
        - JSON output for all logs
        - Automatic trace_id propagation
        - Stack traces for errors
        - ISO timestamps
        - Service name in every log entry
    """

    level = getattr(logging, log_level.upper(), logging.INFO)

    def add_service_name(logger, method_name, event_dict):
        event_dict["service"] = service_name
        return event_dict

    shared_processors = [
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        add_service_name,  # ✅ Service name in every log
        structlog.contextvars.merge_contextvars,  # ✅ Collect trace_id, client_ip
        structlog.processors.TimeStamper(fmt="iso"),  # ✅ ISO timestamps
        structlog.processors.dict_tracebacks,  # ✅ Error tracking
        structlog.processors.format_exc_info,  # ✅ Capture stack traces
        structlog.processors.JSONRenderer(),  # ✅ JSON output
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

    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(logger_name)
        log.handlers = [handler]
        log.propagate = False


def get_logger(name: str):
    """
    Get a structured logger for a module.
    
    Args:
        name: Module name (typically __name__)
    
    Returns:
        structlog logger instance
    
    Example:
        logger = get_logger(__name__)
        logger.info("user_action", user_id=123, action="login")
    """
    return structlog.get_logger(name)
