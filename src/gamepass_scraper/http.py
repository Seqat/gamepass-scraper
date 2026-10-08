"""HTTP helpers: a configured client and requests with retry and backoff."""

from __future__ import annotations

import logging
import math
import time
from typing import Any

import httpx

from gamepass_scraper import __version__
from gamepass_scraper.errors import SourceError

logger = logging.getLogger(__name__)

USER_AGENT = f"gamepass-scraper/{__version__} (+https://github.com/seqat/gamepass-scraper)"
MAX_RETRY_DELAY = 30.0
RETRYABLE_STATUS_CODES = frozenset({429, *range(500, 600)})

# Module-level indirection so tests can replace it without real waiting.
_sleep = time.sleep


def make_client(timeout: float) -> httpx.Client:
    """Create an HTTP client with the scraper's User-Agent and redirect handling."""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        },
    )


def request_with_retry(
    client: httpx.Client,
    url: str,
    params: dict[str, str] | None = None,
    attempts: int = 3,
    backoff: float = 1.0,
) -> httpx.Response:
    """GET ``url`` and return the response, retrying transient failures.

    Network errors, HTTP 429 and HTTP 5xx are retried with exponential backoff, honouring a
    numeric ``Retry-After`` header (capped at 30 seconds). Other 4xx responses fail at once.

    Raises:
        SourceError: on a non-retryable status, or when every attempt has failed.
    """
    reason = "no attempts made"
    for attempt in range(1, attempts + 1):
        retry_after: float | None = None
        try:
            response = client.get(url, params=params)
        except httpx.TransportError as exc:
            reason = f"network error ({type(exc).__name__}: {exc})"
        else:
            if response.status_code < 400:
                return response
            if response.status_code not in RETRYABLE_STATUS_CODES:
                raise SourceError(f"HTTP {response.status_code} from {url}")
            reason = f"HTTP {response.status_code}"
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))

        if attempt == attempts:
            break
        delay = retry_after if retry_after is not None else backoff * 2 ** (attempt - 1)
        delay = min(delay, MAX_RETRY_DELAY)
        logger.info("Request to %s failed (%s); retrying in %.1fs", url, reason, delay)
        _sleep(delay)

    raise SourceError(f"giving up on {url} after {attempts} attempts: {reason}")


def get_json(client: httpx.Client, url: str, params: dict[str, str] | None = None) -> Any:
    """GET ``url`` and decode the JSON body."""
    response = request_with_retry(client, url, params=params)
    try:
        return response.json()
    except ValueError as exc:
        raise SourceError(f"invalid JSON from {url}: {exc}") from exc


def get_text(client: httpx.Client, url: str, params: dict[str, str] | None = None) -> str:
    """GET ``url`` and return the decoded body text."""
    return request_with_retry(client, url, params=params).text


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)
