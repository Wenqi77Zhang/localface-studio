"""Structured logging that only accepts an explicit metadata allowlist."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

LOGGER_NAME = "localface"
SAFE_FIELDS = frozenset(
    {"duration_ms", "error_type", "method", "request_id", "route", "status_code"}
)
_WINDOWS_USER_PATH = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+(?:\\[^\s,;]+)*")
_POSIX_USER_PATH = re.compile(r"(?i)(?:/home/|/Users/)[^\s,;]+")
_SECRET_VALUE = re.compile(
    r"(?i)\b(authorization|cookie|token|secret|password|api[_-]?key)\s*[:=]\s*([^\s,;]+)"
)
_KNOWN_TOKEN = re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]+\b")


def redact_text(value: object) -> str:
    """Remove common secrets and user-specific absolute paths from a value."""
    text = str(value)
    text = _WINDOWS_USER_PATH.sub("[REDACTED_PATH]", text)
    text = _POSIX_USER_PATH.sub("[REDACTED_PATH]", text)
    text = _SECRET_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return _KNOWN_TOKEN.sub("[REDACTED_TOKEN]", text)


class PrivacyJsonFormatter(logging.Formatter):
    """Emit one JSON object per event without traceback or arbitrary extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": redact_text(record.getMessage()),
        }
        fields = getattr(record, "safe_fields", {})
        if isinstance(fields, dict):
            for key, value in fields.items():
                if key in SAFE_FIELDS:
                    payload[key] = value if isinstance(value, (int, float)) else redact_text(value)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str) -> logging.Logger:
    """Configure only the application logger, leaving host logging untouched."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(PrivacyJsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: int, event: str, **fields: object) -> None:
    """Log an event while dropping all metadata outside the allowlist."""
    logger.log(level, event, extra={"safe_fields": fields})
