"""
shared/logging_config.py

Structured JSON logging setup for all StreamRec services.
JSON logs are compatible with CloudWatch Logs Insights and Grafana Loki.
"""

import logging
import sys
from typing import Any

try:
    import structlog
    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False


def configure_logging(service_name: str, level: str = "INFO") -> None:
    """
    Configure structured logging for a service.

    Args:
        service_name: Identifies the service in every log line.
        level: Log level string ("DEBUG", "INFO", "WARNING", "ERROR").
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    if _HAS_STRUCTLOG:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        )
    else:
        # Fallback to stdlib with a JSON-ish format
        logging.basicConfig(
            level=log_level,
            format='{"time":"%(asctime)s","level":"%(levelname)s","service":"'
                   + service_name
                   + '","logger":"%(name)s","message":"%(message)s"}',
            stream=sys.stdout,
        )


def get_logger(name: str) -> Any:
    """Return a logger (structlog or stdlib) for the given name."""
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return logging.getLogger(name)
