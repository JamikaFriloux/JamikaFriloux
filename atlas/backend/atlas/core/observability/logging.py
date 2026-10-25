"""Structured JSON logging with secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping
from typing import Any

import structlog

_SENSITIVE_KEYS = re.compile(
    r"(secret|password|passwd|token|api[_-]?key|authorization|cookie|dsn|credential)", re.I
)
# Values that look like credentials even under innocuous keys.
_SENSITIVE_VALUES = [
    re.compile(r"\b(PK|AK)[A-Z0-9]{16,}\b"),  # Alpaca key IDs
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),  # Anthropic keys
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b"),  # Telegram bot tokens
    re.compile(r"/bot[^/\s]+/"),  # Telegram Bot API URLs embed the token in the path
    re.compile(r"Bearer\s+[A-Za-z0-9\-_\.=]+", re.I),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWTs
]
REDACTED = "[REDACTED]"


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        for pattern in _SENSITIVE_VALUES:
            value = pattern.sub(REDACTED, value)
        return value
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list | tuple):
        return type(value)(redact_value(v) for v in value)
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: (REDACTED if _SENSITIVE_KEYS.search(str(k)) else redact_value(v))
        for k, v in data.items()
    }


def _redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return redact_mapping(event_dict)


class _RedactingFilter(logging.Filter):
    """Applies value redaction to stdlib log records from third-party libraries."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact_value(message)
        record.args = None
        return True


def configure_logging(level: str = "INFO", json: bool = True, service: str = "atlas") -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
        _redact_processor,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service)
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RedactingFilter())
    root.handlers = [handler]
    # httpx logs full request URLs at INFO; Telegram URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
