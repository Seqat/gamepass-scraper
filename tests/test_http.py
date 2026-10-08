"""Tests for the HTTP helpers: client configuration, retries, backoff and error mapping."""

from __future__ import annotations

import httpx
import pytest
import respx

from gamepass_scraper import __version__
from gamepass_scraper.errors import SourceError
from gamepass_scraper.http import (
    MAX_RETRY_DELAY,
    USER_AGENT,
    get_json,
    get_text,
    make_client,
    request_with_retry,
)

URL = "https://api.example.com/resource"


def test_make_client_sets_user_agent_accept_and_redirects() -> None:
    with make_client(timeout=7.5) as client:
        assert client.headers["User-Agent"] == USER_AGENT
        assert "application/json" in client.headers["Accept"]
        assert client.follow_redirects is True
        assert client.timeout.read == 7.5


def test_user_agent_names_package_and_version() -> None:
    assert USER_AGENT.startswith(f"gamepass-scraper/{__version__} ")
    assert "github.com/seqat/gamepass-scraper" in USER_AGENT


def test_user_agent_is_sent_on_requests(mock_api: respx.MockRouter, client: httpx.Client) -> None:
    route = mock_api.get(URL).mock(return_value=httpx.Response(200, text="ok"))
    get_text(client, URL)
    assert route.calls.last.request.headers["User-Agent"] == USER_AGENT


def test_redirects_are_followed(mock_api: respx.MockRouter, client: httpx.Client) -> None:
    mock_api.get(URL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://api.example.com/final"})
    )
    mock_api.get("https://api.example.com/final").mock(
        return_value=httpx.Response(200, json={"done": True})
    )
    assert get_json(client, URL) == {"done": True}


def test_query_params_are_passed_through(mock_api: respx.MockRouter, client: httpx.Client) -> None:
    route = mock_api.get(URL).mock(return_value=httpx.Response(200, text="ok"))
    request_with_retry(client, URL, params={"id": "abc", "market": "US"})
    assert route.calls.last.request.url.params["id"] == "abc"
    assert route.calls.last.request.url.params["market"] == "US"


def test_retries_503_then_succeeds(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    route = mock_api.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": 1})]
    )

    assert get_json(client, URL) == {"ok": 1}
    assert route.call_count == 2
    assert sleeps == [1.0]


def test_429_honours_numeric_retry_after(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    mock_api.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, text="ok"),
        ]
    )
    assert get_text(client, URL) == "ok"
    assert sleeps == [7.0]


def test_retry_after_is_capped(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    mock_api.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3600"}),
            httpx.Response(200, text="ok"),
        ]
    )
    get_text(client, URL)
    assert sleeps == [MAX_RETRY_DELAY] == [30.0]


@pytest.mark.parametrize("header", ["soon", "nan", "inf", ""])
def test_unusable_retry_after_falls_back_to_backoff(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float], header: str
) -> None:
    mock_api.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": header}),
            httpx.Response(200, text="ok"),
        ]
    )
    get_text(client, URL)
    assert sleeps == [1.0]


def test_negative_retry_after_is_clamped_to_zero(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    mock_api.get(URL).mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": "-5"}),
            httpx.Response(200, text="ok"),
        ]
    )
    get_text(client, URL)
    assert sleeps == [0.0]


def test_exponential_backoff_then_source_error(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    route = mock_api.get(URL).mock(return_value=httpx.Response(500))

    with pytest.raises(SourceError, match=r"giving up on .* after 3 attempts: HTTP 500"):
        request_with_retry(client, URL)

    assert route.call_count == 3
    assert sleeps == [1.0, 2.0]


def test_custom_attempts_and_backoff(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    route = mock_api.get(URL).mock(return_value=httpx.Response(502))

    with pytest.raises(SourceError):
        request_with_retry(client, URL, attempts=4, backoff=0.5)

    assert route.call_count == 4
    assert sleeps == [0.5, 1.0, 2.0]


def test_backoff_delay_is_capped(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    mock_api.get(URL).mock(return_value=httpx.Response(503))

    with pytest.raises(SourceError):
        request_with_retry(client, URL, attempts=3, backoff=100.0)

    assert sleeps == [MAX_RETRY_DELAY, MAX_RETRY_DELAY]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410])
def test_non_retryable_4xx_fails_immediately(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float], status: int
) -> None:
    route = mock_api.get(URL).mock(return_value=httpx.Response(status))

    with pytest.raises(SourceError, match=f"HTTP {status} from"):
        request_with_retry(client, URL)

    assert route.call_count == 1
    assert sleeps == []


@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_transport_error_retries_then_source_error(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float], exc: Exception
) -> None:
    route = mock_api.get(URL).mock(side_effect=exc)

    with pytest.raises(SourceError, match="network error") as info:
        request_with_retry(client, URL)

    assert route.call_count == 3
    assert sleeps == [1.0, 2.0]
    assert type(exc).__name__ in str(info.value)


def test_transport_error_then_success(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    mock_api.get(URL).mock(
        side_effect=[httpx.ConnectError("reset"), httpx.Response(200, text="ok")]
    )
    assert get_text(client, URL) == "ok"
    assert sleeps == [1.0]


def test_single_attempt_does_not_sleep(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    mock_api.get(URL).mock(return_value=httpx.Response(503))

    with pytest.raises(SourceError, match="after 1 attempts"):
        request_with_retry(client, URL, attempts=1)
    assert sleeps == []


def test_get_json_invalid_body_is_source_error(
    mock_api: respx.MockRouter, client: httpx.Client
) -> None:
    mock_api.get(URL).mock(return_value=httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(SourceError, match="invalid JSON"):
        get_json(client, URL)


def test_get_text_returns_decoded_body(mock_api: respx.MockRouter, client: httpx.Client) -> None:
    mock_api.get(URL).mock(
        return_value=httpx.Response(
            200, content="Pokémon".encode(), headers={"Content-Type": "text/plain; charset=utf-8"}
        )
    )
    assert get_text(client, URL) == "Pokémon"
