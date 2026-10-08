"""Fallback source: scrape the game list from https://gamepasscounter.com/.

This is the legacy behaviour of the original script. It only provides the PC list, and
its XPath is unverified against the current site layout.
"""

from __future__ import annotations

import httpx
import lxml.etree
import lxml.html

from gamepass_scraper.errors import SourceError
from gamepass_scraper.http import get_text
from gamepass_scraper.models import Game

PAGE_URL = "https://gamepasscounter.com/"
LIST_XPATH = '//*[@id="row2"]/div[2]/div[3]/div/ul'
SOURCE_NAME = "gamepasscounter"


def fetch_games(client: httpx.Client) -> list[Game]:
    """Download the PC game list from gamepasscounter.com."""
    return parse_games(get_text(client, PAGE_URL))


def parse_games(html: str) -> list[Game]:
    """Extract PC game titles from the page HTML.

    Raises:
        SourceError: if the list element is missing or contains no titles.
    """
    try:
        document = lxml.html.document_fromstring(html)
    except (lxml.etree.ParserError, ValueError) as exc:
        raise SourceError(f"could not parse the gamepasscounter.com page: {exc}") from exc

    nodes = document.xpath(LIST_XPATH)
    if not nodes:
        raise SourceError("could not find the game list on gamepasscounter.com (layout changed?)")
    container = nodes[0]

    items = [item.text_content() for item in container.xpath(".//li")]
    if not items:
        items = container.text_content().splitlines()

    titles: list[str] = []
    seen: set[str] = set()
    for item in items:
        title = " ".join(item.split())
        if title and title not in seen:
            seen.add(title)
            titles.append(title)

    if not titles:
        raise SourceError("the gamepasscounter.com game list is empty")
    return [Game(title=title, lists=("pc",), source=SOURCE_NAME) for title in titles]
