"""JSON-line logging for AutoMaxFix."""

from __future__ import annotations

import json
import logging
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

LOGGER_NAME = "automaxfix"

_configured = False
_lock = threading.Lock()


def configure_logging(level: str = "INFO") -> None:
    global _configured
    with _lock:
        if _configured:
            return
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
        root.addHandler(handler)
        root.setLevel(getattr(logging, level.upper(), logging.INFO))
        _configured = True


def get_logger(component: str) -> "_BoundLogger":
    configure_logging()
    return _BoundLogger(logging.getLogger(f"{LOGGER_NAME}.{component}"), component)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


@dataclass
class _BoundLogger:
    base: logging.Logger
    component: str

    def _emit(self, level: int, message: str, **fields: Any) -> None:
        extra = {"extra_fields": {"component": self.component, **fields}}
        self.base.log(level, message, extra=extra)

    def debug(self, message: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._emit(logging.INFO, message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._emit(logging.WARNING, message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self._emit(logging.ERROR, message, **fields)

    def critical(self, message: str, **fields: Any) -> None:
        self._emit(logging.CRITICAL, message, **fields)
