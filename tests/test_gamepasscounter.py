"""Tests for the gamepasscounter.com fallback source."""

from __future__ import annotations

import httpx
import pytest
import respx

from gamepass_scraper.errors import SourceError
from gamepass_scraper.sources import gamepasscounter
from gamepass_scraper.sources.gamepasscounter import PAGE_URL, fetch_games, parse_games

FIXTURE_TITLES = ["Pixel Harbor", "Quiet Fjord", "Ember & Ash"]


def test_parse_games_extracts_unique_non_blank_titles(gamepasscounter_html: str) -> None:
    games = parse_games(gamepasscounter_html)

    assert [g.title for g in games] == FIXTURE_TITLES
    assert all(g.lists == ("pc",) for g in games)
    assert all(g.source == "gamepasscounter" for g in games)
    assert all(g.product_id is None for g in games)


def test_parse_games_collapses_internal_whitespace(gamepasscounter_html: str) -> None:
    titles = [g.title for g in parse_games(gamepasscounter_html)]
    assert "Quiet Fjord" in titles  # source markup was "Quiet   Fjord"


def _page_with_list(inner: str) -> str:
    """Wrap ``inner`` where the legacy XPath ``//*[@id="row2"]/div[2]/div[3]/div/ul`` expects it."""
    return (
        '<html><body><div id="row2"><div>left</div><div>'
        "<div>intro</div><div>filler</div><div>"
        f"<div>{inner}</div>"
        "</div></div></div></body></html>"
    )


def test_parse_games_uses_ul_text_when_no_list_items() -> None:
    html = _page_with_list("<ul>\n  Pixel Harbor\n  Quiet Fjord\n  Pixel Harbor\n</ul>")
    assert [g.title for g in parse_games(html)] == ["Pixel Harbor", "Quiet Fjord"]


def test_parse_games_missing_list_raises_source_error() -> None:
    html = "<html><body><div id='row1'><ul><li>Not the right list</li></ul></div></body></html>"
    with pytest.raises(SourceError, match="could not find the game list"):
        parse_games(html)


def test_parse_games_list_with_only_blank_items_raises_source_error() -> None:
    html = _page_with_list("<ul><li>  </li><li></li></ul>")
    with pytest.raises(SourceError, match="empty"):
        parse_games(html)


@pytest.mark.parametrize(
    "html",
    [
        "",
        "   \n  ",
        # lxml refuses unicode strings that carry an encoding declaration.
        '<?xml version="1.0" encoding="utf-8"?><html></html>',
    ],
)
def test_parse_games_unparseable_document_raises_source_error(html: str) -> None:
    with pytest.raises(SourceError):
        parse_games(html)


def test_fetch_games_downloads_and_parses_page(
    mock_api: respx.MockRouter, client: httpx.Client, gamepasscounter_html: str
) -> None:
    route = mock_api.get(PAGE_URL).mock(return_value=httpx.Response(200, text=gamepasscounter_html))

    games = fetch_games(client)

    assert route.call_count == 1
    assert [g.title for g in games] == FIXTURE_TITLES


def test_fetch_games_http_failure_is_source_error(
    mock_api: respx.MockRouter, client: httpx.Client, sleeps: list[float]
) -> None:
    mock_api.get(PAGE_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(SourceError, match="giving up"):
        fetch_games(client)
    assert len(sleeps) == 2  # three attempts, two waits


def test_source_name_constant() -> None:
    assert gamepasscounter.SOURCE_NAME == "gamepasscounter"
