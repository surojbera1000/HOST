"""Structured logging with automatic secret redaction."""
import logging
import re

import structlog

# These patterns are redacted from logs (to prevent secret leaks)
_SENSITIVE_KEYS = re.compile(
    r"(token|secret|api_hash|password|fernet|bot_token|api_key)", re.IGNORECASE
)


def _redact(_, __, event_dict):
    for key in list(event_dict.keys()):
        if _SENSITIVE_KEYS.search(key):
            event_dict[key] = "***REDACTED***"
    return event_dict


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact,
            structlog.dev.ConsoleRenderer(),
        ],
    )


def get_logger(name: str = "app"):
    return structlog.get_logger(name)
