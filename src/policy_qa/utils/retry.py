"""Shared retry policy for transient Azure / OpenAI failures.

Single source of truth for what counts as retryable and how to back off,
used by every outbound Azure call (embeddings, search).
"""

from __future__ import annotations

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

TRANSIENT_STATUS_CODES = (429, 500, 502, 503, 504)


def is_transient_error(exc: BaseException) -> bool:
    """Return True for rate-limit and server-side errors worth retrying."""
    return getattr(exc, "status_code", None) in TRANSIENT_STATUS_CODES


def transient_retry(*, attempts: int, max_wait: float):
    """Build a tenacity decorator with jittered exponential backoff.

    Args:
        attempts: Total tries before the error is re-raised.
        max_wait: Upper bound in seconds for a single backoff sleep.
    """
    return retry(
        retry=retry_if_exception(is_transient_error),
        wait=wait_exponential_jitter(initial=1, max=max_wait),
        stop=stop_after_attempt(attempts),
        reraise=True,
    )
