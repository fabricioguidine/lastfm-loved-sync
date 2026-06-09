from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def is_retryable(exc: BaseException) -> bool:
    """Transport errors and Last.fm's intermittent 5xx responses are worth retrying."""
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


resilient = retry(
    retry=retry_if_exception(is_retryable),
    wait=wait_exponential(multiplier=0.5, max=8),
    stop=stop_after_attempt(8),
    reraise=True,
)
