"""Primary source: Microsoft's public (undocumented) Game Pass catalog endpoints.

These endpoints are not documented by Microsoft and may change without notice.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import httpx

from gamepass_scraper.errors import SourceError
from gamepass_scraper.http import get_json
from gamepass_scraper.lists import GAME_LISTS
from gamepass_scraper.models import Game, merge_games

logger = logging.getLogger(__name__)

CATALOG_URL = "https://catalog.gamepass.com/sigls/v2"
PRODUCTS_URL = "https://displaycatalog.mp.microsoft.com/v7.0/products"
IMAGE_PURPOSE_PREFERENCE = ("Poster", "BoxArt", "TitledHeroArt")
MIN_RELEASE_YEAR = 1900
SOURCE_NAME = "microsoft"


def fetch_list_ids(client: httpx.Client, sigl_id: str, market: str, language: str) -> list[str]:
    """Return the product IDs in one SIGL list, in catalog order."""
    payload = get_json(
        client,
        CATALOG_URL,
        params={"id": sigl_id, "language": language, "market": market},
    )
    return parse_sigl_ids(payload)


def parse_sigl_ids(payload: object) -> list[str]:
    """Extract de-duplicated product IDs from a SIGL response.

    The first element is list metadata and is skipped; every later element with an ``id``
    key is a product reference.

    Raises:
        SourceError: if the payload is not a list or contains no product IDs.
    """
    if not isinstance(payload, list):
        raise SourceError("unexpected response from the Game Pass catalog (not a list)")
    ids: list[str] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or "id" not in item:
            continue
        product_id = _text(item.get("id"))
        if product_id is not None and product_id not in seen:
            seen.add(product_id)
            ids.append(product_id)
    if not ids:
        raise SourceError("the Game Pass catalog list returned no product IDs")
    return ids


def fetch_product_details(
    client: httpx.Client,
    product_ids: Sequence[str],
    market: str,
    language: str,
    batch_size: int,
) -> list[dict[str, Any]]:
    """Fetch raw product records from the display catalog, in batches."""
    products: list[dict[str, Any]] = []
    for start in range(0, len(product_ids), batch_size):
        batch = product_ids[start : start + batch_size]
        payload = get_json(
            client,
            PRODUCTS_URL,
            params={"bigIds": ",".join(batch), "market": market, "languages": language},
        )
        raw = payload.get("Products") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            raise SourceError("unexpected response from the Microsoft product details endpoint")
        products.extend(product for product in raw if isinstance(product, dict))
    return products


def parse_product(product: Mapping[str, Any], lists: Sequence[str]) -> Game | None:
    """Convert one raw display-catalog product into a ``Game``.

    Returns None when the product has neither a title nor an ID.
    """
    product_id = _text(product.get("ProductId"))
    props = _first_mapping(product.get("LocalizedProperties"))
    market_props = _first_mapping(product.get("MarketProperties"))
    details = _mapping(product.get("Properties"))

    title = _text(props.get("ProductTitle")) or product_id
    if title is None:
        return None

    categories = details.get("Categories")
    if not isinstance(categories, list):
        categories = [details.get("Category")]

    return Game(
        title=title,
        product_id=product_id,
        developer=_text(props.get("DeveloperName")),
        publisher=_text(props.get("PublisherName")),
        release_date=parse_release_date(market_props.get("OriginalReleaseDate")),
        categories=tuple(c for c in (_text(c) for c in categories) if c),
        image_url=pick_image_url(props.get("Images")),
        lists=tuple(sorted(set(lists))),
        source=SOURCE_NAME,
    )


def parse_release_date(value: object) -> date | None:
    """Parse a timestamp such as ``2020-11-10T00:00:00.0000000Z``.

    Returns None for invalid values and for placeholder dates before 1900.
    """
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = date.fromisoformat(text[:10])
    except ValueError:
        return None
    return parsed if parsed.year >= MIN_RELEASE_YEAR else None


def pick_image_url(images: object) -> str | None:
    """Choose the best image URL: Poster, then BoxArt, then TitledHeroArt, then the first."""
    if not isinstance(images, list):
        return None
    candidates = [
        (_text(image.get("ImagePurpose")), _image_uri(image))
        for image in images
        if isinstance(image, dict) and _image_uri(image) is not None
    ]
    for purpose in IMAGE_PURPOSE_PREFERENCE:
        for candidate_purpose, uri in candidates:
            if candidate_purpose == purpose:
                return uri
    return candidates[0][1] if candidates else None


def fetch_games(
    client: httpx.Client,
    list_names: Sequence[str],
    sigl_ids: Sequence[str],
    market: str,
    language: str,
    batch_size: int,
) -> list[Game]:
    """Fetch every requested list and return the merged, sorted games.

    Product details are fetched once per unique ID. Extra SIGL IDs are labelled
    ``sigl:<id>``.
    """
    lists_to_fetch = [(name, GAME_LISTS[name]) for name in list_names]
    lists_to_fetch += [(f"sigl:{sigl_id}", sigl_id) for sigl_id in sigl_ids]

    membership: dict[str, list[str]] = {}
    for list_name, sigl_id in lists_to_fetch:
        ids = fetch_list_ids(client, sigl_id, market, language)
        logger.debug("List %s contains %d product IDs", list_name, len(ids))
        for product_id in ids:
            membership.setdefault(product_id, []).append(list_name)

    products = fetch_product_details(client, list(membership), market, language, batch_size)
    by_id: dict[str, dict[str, Any]] = {}
    for product in products:
        product_id = _text(product.get("ProductId"))
        if product_id is not None:
            by_id.setdefault(product_id, product)

    games: list[Game] = []
    for product_id, names in membership.items():
        product = by_id.get(product_id)
        if product is None:
            logger.debug("Product %s missing from the catalog response; skipped", product_id)
            continue
        game = parse_product(product, names)
        if game is not None:
            games.append(game)
    return merge_games(games)


def _image_uri(image: Mapping[str, Any]) -> str | None:
    uri = _text(image.get("Uri"))
    if uri is None:
        return None
    return f"https:{uri}" if uri.startswith("//") else uri


def _text(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], Mapping):
        return value[0]
    return {}
