"""Structured JSON logging with a per-query correlation id.

Every agent hop logs a single JSON line containing the agent name, its input,
its output and latency, tagged with the correlation id of the originating
query so a full request can be reconstructed from the log stream.
"""

from __future__ import annotations

import contextvars
import json
import logging
from logging.handlers import RotatingFileHandler
import sys
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
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


def setup_logging(
    level: str = "INFO",
    log_file: Path | str = "logs/policy-qa.jsonl",
    log_to_console: bool = False,
) -> None:
    """Write structured logs to a rotating JSONL file.

    Console logging is opt-in so normal CLI output stays human-readable while
    the complete input/output audit trail remains available for inspection.
    """
    # Agent Framework currently emits these two experimental-feature warnings
    # on import. They are dependency status notices, not actionable runtime
    # warnings for CLI users. Keep every other warning visible.
    warnings.filterwarnings(
        "ignore",
        message=r"\[(SKILLS|HARNESS)\].*experimental.*",
        category=Warning,
        module=r"agent_framework\..*",
    )

    formatter = JsonFormatter()
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(file_handler)
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)
    root.setLevel(level)
    # Dependency logs are noisy; application-level agent input/output events
    # already capture the useful workflow audit trail.
    logging.getLogger("agent_framework").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def log_event(logger: logging.Logger, message: str, **event: Any) -> None:
    """Log a structured event as a JSON line."""
    logger.info(message, extra={"event": event})
