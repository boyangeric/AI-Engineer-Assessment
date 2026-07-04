"""Structured JSON logging with a per-query correlation id.

Every agent hop logs a single JSON line containing the agent name, its input,
its output and latency, tagged with the correlation id of the originating
query so a full request can be reconstructed from the log stream.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)


def new_correlation_id() -> str:
    cid = uuid.uuid4().hex[:12]
    correlation_id_var.set(cid)
    return cid


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }
        extra = getattr(record, "event", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Azure SDK HTTP logging is very chatty at INFO.
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def log_event(logger: logging.Logger, message: str, **event: Any) -> None:
    """Log a structured event as a JSON line."""
    logger.info(message, extra={"event": event})
