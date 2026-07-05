"""Dependency-free helpers shared across the package.

Everything in here is a leaf: these modules import nothing from the rest of
`policy_qa`, so any layer (ingestion, search, agents, evaluation) may use them
without creating an upward dependency.
"""

from .logging_setup import log_event, new_correlation_id, setup_logging
from .retry import is_transient_error, transient_retry
from .text import (
    escape_untrusted,
    normalize_control_id,
    tokenize_words,
    wrap_untrusted_document,
)

__all__ = [
    "escape_untrusted",
    "is_transient_error",
    "log_event",
    "new_correlation_id",
    "normalize_control_id",
    "setup_logging",
    "tokenize_words",
    "transient_retry",
    "wrap_untrusted_document",
]
