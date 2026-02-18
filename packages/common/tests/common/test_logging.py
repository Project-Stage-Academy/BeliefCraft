"""
Unit tests for logging configuration.

Run:
    pytest packages/common/tests/test_logging.py -v
"""

# mypy: disallow-untyped-defs=False, check-untyped-defs=False

import json
import logging

import common.logging as common_logging
import pytest
import structlog
from common.logging import configure_logging, get_logger


class TestLoggingConfiguration:
    """Test structured logging setup"""

    def test_configure_logging_sets_service_name(self, capsys):
        """Service name should appear in every log entry"""
        configure_logging("test-service", "INFO")
        logger = get_logger("test_module")

        logger.info("test_event", test_key="test_value")

        # Capture stdout
        captured = capsys.readouterr()
        log_dict = json.loads(captured.out.strip())

        assert log_dict["service"] == "test-service"
        assert log_dict["event"] == "test_event"
        assert log_dict["test_key"] == "test_value"

    def test_log_level_configuration(self):
        """Log level should be configurable"""
        configure_logging("test-service", "WARNING")

        # Check root logger level
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

    def test_json_output_structure(self, capsys):
        """Logs should be valid JSON with required fields"""
        configure_logging("test-service", "INFO")
        logger = get_logger("test_module")

        logger.info("test_event", user_id=123)

        captured = capsys.readouterr()
        log_dict = json.loads(captured.out.strip())

        # Required fields
        assert "timestamp" in log_dict
        assert "level" in log_dict
        assert "service" in log_dict
        assert "event" in log_dict
        assert log_dict["level"] == "info"

    def test_error_logging_includes_exc_info(self, capsys):
        """Error logs should include exception information"""
        configure_logging("test-service", "ERROR")
        logger = get_logger("test_module")

        try:
            raise ValueError("Test error")
        except ValueError:
            logger.error("error_occurred", exc_info=True)

        captured = capsys.readouterr()
        log_dict = json.loads(captured.out.strip())
        assert "exception" in log_dict or "exc_info" in log_dict

    def test_contextvars_binding(self, capsys):
        """Context vars should be included in logs"""
        configure_logging("test-service", "INFO")
        logger = get_logger("test_module")

        structlog.contextvars.bind_contextvars(trace_id="test-trace-123", client_ip="192.168.1.1")

        logger.info("test_event")

        captured = capsys.readouterr()
        log_dict = json.loads(captured.out.strip())
        assert log_dict["trace_id"] == "test-trace-123"
        assert log_dict["client_ip"] == "192.168.1.1"

        structlog.contextvars.clear_contextvars()

    def test_get_logger_returns_structlog_instance(self):
        """get_logger should return a structlog logger"""
        configure_logging("test-service", "INFO")
        logger = get_logger("test_module")

        assert hasattr(logger, "bind")
        assert callable(logger.bind)

    def test_configure_logging_idempotent(self, capsys):
        """configure_logging should be idempotent (multiple calls safe)"""
        configure_logging("test-service-1", "INFO")
        logger1 = get_logger("test")
        logger1.info("first_call")

        captured1 = capsys.readouterr()
        log1 = json.loads(captured1.out.strip())
        assert log1["service"] == "test-service-1"

        # Second call should not reconfigure
        configure_logging("test-service-2", "DEBUG")
        logger2 = get_logger("test")
        logger2.info("second_call")

        captured2 = capsys.readouterr()
        log2 = json.loads(captured2.out.strip())
        # Should still be test-service-1 (not reconfigured)
        assert log2["service"] == "test-service-1"


class TestLoggerUsage:
    """Test common logging patterns"""

    def test_info_logging_with_metadata(self, capsys):
        """Info logs should accept arbitrary metadata"""
        configure_logging("test-service", "INFO")
        logger = get_logger(__name__)

        logger.info("user_action", user_id=123, action="login", ip="192.168.1.1")

        captured = capsys.readouterr()
        log_dict = json.loads(captured.out.strip())
        assert log_dict["user_id"] == 123
        assert log_dict["action"] == "login"
        assert log_dict["ip"] == "192.168.1.1"

    def test_warning_logging(self, capsys):
        """Warning logs should work correctly"""
        configure_logging("test-service", "WARNING")
        logger = get_logger(__name__)

        logger.warning("high_latency", duration_ms=5000, threshold=1000)

        captured = capsys.readouterr()
        log_dict = json.loads(captured.out.strip())

        assert log_dict["level"] == "warning"
        assert log_dict["duration_ms"] == 5000

    def test_debug_logging_filtered_by_level(self, capsys):
        """Debug logs should be filtered when level is INFO"""
        configure_logging("test-service", "INFO")
        logger = get_logger(__name__)

        logger.debug("debug_message")
        logger.info("info_message")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]

        assert len(lines) == 1
        log_dict = json.loads(lines[0])
        assert log_dict["event"] == "info_message"


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration between tests"""
    # Reset before test
    common_logging._configured = False
    logging.root.handlers = []
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()

    yield

    # Reset after test
    common_logging._configured = False
    structlog.reset_defaults()
    logging.root.handlers = []
    structlog.contextvars.clear_contextvars()
