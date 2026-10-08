"""Tests for the Microsoft catalog source, using mocked endpoints only."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
import respx

from gamepass_scraper.errors import SourceError
from gamepass_scraper.lists import GAME_LISTS
from gamepass_scraper.models import Game
from gamepass_scraper.sources import microsoft
from gamepass_scraper.sources.microsoft import (
    CATALOG_URL,
    PRODUCTS_URL,
    fetch_games,
    fetch_list_ids,
    fetch_product_details,
    parse_product,
    parse_release_date,
    parse_sigl_ids,
    pick_image_url,
)

PC_IDS = ["9NBLGGH4R315", "9PFZWPPG2HZ8", "9NZ9Q8N8NC2Z", "9P8GB3D2SZ5K"]
CONSOLE_IDS = ["9NZ9Q8N8NC2Z", "9MZ1SNWT0N5D", "9N7TCNNW7C7N"]


def _product(products: list[dict[str, Any]], product_id: str) -> dict[str, Any]:
    return next(p for p in products if p["ProductId"] == product_id)


# --- parse_sigl_ids -------------------------------------------------------------------------


def test_parse_sigl_ids_skips_metadata_and_dedupes_in_order(sigl_pc: list[Any]) -> None:
    assert parse_sigl_ids(sigl_pc) == PC_IDS


def test_parse_sigl_ids_console_fixture(sigl_console: list[Any]) -> None:
    assert parse_sigl_ids(sigl_console) == CONSOLE_IDS


def test_parse_sigl_ids_strips_whitespace() -> None:
    assert parse_sigl_ids([{"siglId": "x"}, {"id": "  ABC123  "}]) == ["ABC123"]


@pytest.mark.parametrize(
    "payload",
    [
        {"id": "9NBLGGH4R315"},  # a dict, not a list
        "9NBLGGH4R315",
        None,
        42,
        [],  # empty list
        [{"siglId": "only-metadata", "title": "Empty"}],  # metadata, no product IDs
        [{"id": None}, {"id": ""}, {"id": "   "}],  # IDs that are blank after cleaning
        [{"id": 12345}],  # non-string ID
        ["9NBLGGH4R315", 1, None],  # bare values, not objects
    ],
)
def test_parse_sigl_ids_bad_payload_raises_source_error(payload: object) -> None:
    with pytest.raises(SourceError):
        parse_sigl_ids(payload)


# --- parse_release_date ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2020-11-10T00:00:00.0000000Z", date(2020, 11, 10)),
        ("2021-03-02", date(2021, 3, 2)),
        ("1900-01-01T00:00:00Z", date(1900, 1, 1)),  # boundary is kept
    ],
)
def test_parse_release_date_valid(value: str, expected: date) -> None:
    assert parse_release_date(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "1601-01-01T00:00:00.0000000Z",  # placeholder date
        "1899-12-31T00:00:00Z",  # before the cut-off year
        "2020-13-01T00:00:00Z",  # invalid month
        "not-a-date",
        "",
        "   ",
        None,
        20201110,
    ],
)
def test_parse_release_date_invalid_returns_none(value: object) -> None:
    assert parse_release_date(value) is None


# --- pick_image_url -------------------------------------------------------------------------


def test_pick_image_url_prefers_poster_then_boxart_then_hero() -> None:
    images = [
        {"ImagePurpose": "TitledHeroArt", "Uri": "//img.example.com/hero.jpg"},
        {"ImagePurpose": "BoxArt", "Uri": "//img.example.com/box.jpg"},
        {"ImagePurpose": "Poster", "Uri": "//img.example.com/poster.jpg"},
    ]
    assert pick_image_url(images) == "https://img.example.com/poster.jpg"

    assert pick_image_url(images[:2]) == "https://img.example.com/box.jpg"
    assert pick_image_url(images[:1]) == "https://img.example.com/hero.jpg"


def test_pick_image_url_falls_back_to_first_usable_image() -> None:
    images = [
        {"ImagePurpose": "Logo", "Uri": "//img.example.com/logo.png"},
        {"ImagePurpose": "Logo", "Uri": "//img.example.com/logo2.png"},
    ]
    assert pick_image_url(images) == "https://img.example.com/logo.png"


def test_pick_image_url_adds_https_only_to_protocol_relative_uris() -> None:
    assert pick_image_url([{"ImagePurpose": "Poster", "Uri": "https://a.example/p.jpg"}]) == (
        "https://a.example/p.jpg"
    )
    assert pick_image_url([{"ImagePurpose": "Poster", "Uri": "//b.example/p.jpg"}]) == (
        "https://b.example/p.jpg"
    )


def test_pick_image_url_skips_entries_without_usable_uri() -> None:
    images = [
        "not-a-dict",
        {"ImagePurpose": "Poster"},  # no Uri
        {"ImagePurpose": "Poster", "Uri": ""},
        {"ImagePurpose": "BoxArt", "Uri": "//img.example.com/box.jpg"},
    ]
    assert pick_image_url(images) == "https://img.example.com/box.jpg"


@pytest.mark.parametrize("images", [None, [], "//img.example.com/x.jpg", {"Uri": "//x"}, [{}]])
def test_pick_image_url_no_images_returns_none(images: object) -> None:
    assert pick_image_url(images) is None


# --- parse_product --------------------------------------------------------------------------


def test_parse_product_full_record(displaycatalog_products: dict[str, Any]) -> None:
    product = _product(displaycatalog_products["Products"], "9NBLGGH4R315")

    game = parse_product(product, ["pc", "console", "pc"])

    assert game == Game(
        title="Pixel Harbor",
        product_id="9NBLGGH4R315",
        developer="Lumen Studio",
        publisher="Lumen Interactive",
        release_date=date(2020, 11, 10),
        categories=("Action", "Indie"),
        image_url="https://img.example.com/pixel-harbor/poster.jpg",
        lists=("console", "pc"),
        source="microsoft",
    )


def test_parse_product_missing_images(displaycatalog_products: dict[str, Any]) -> None:
    game = parse_product(_product(displaycatalog_products["Products"], "9PFZWPPG2HZ8"), ["pc"])
    assert game is not None
    assert game.title == "Quiet Fjord"
    assert game.image_url is None
    assert game.release_date == date(2021, 3, 2)


def test_parse_product_placeholder_release_date(displaycatalog_products: dict[str, Any]) -> None:
    game = parse_product(_product(displaycatalog_products["Products"], "9NZ9Q8N8NC2Z"), ["pc"])
    assert game is not None
    assert game.release_date is None
    assert game.image_url == "https://img.example.com/starfall/boxart.jpg"


def test_parse_product_only_single_category(displaycatalog_products: dict[str, Any]) -> None:
    game = parse_product(_product(displaycatalog_products["Products"], "9P8GB3D2SZ5K"), ["pc"])
    assert game is not None
    assert game.categories == ("Simulation",)
    assert game.publisher is None


def test_parse_product_falls_back_to_product_id_for_title() -> None:
    game = parse_product({"ProductId": "9ABCDEF12345"}, ["pc"])
    assert game == Game(title="9ABCDEF12345", product_id="9ABCDEF12345", lists=("pc",))


def test_parse_product_without_title_or_id_returns_none() -> None:
    assert parse_product({}, ["pc"]) is None
    assert parse_product({"LocalizedProperties": [{"ProductTitle": "  "}]}, ["pc"]) is None


@pytest.mark.parametrize(
    "product",
    [
        {"ProductId": "X1", "LocalizedProperties": None, "MarketProperties": "oops"},
        {"ProductId": "X1", "LocalizedProperties": [], "MarketProperties": []},
        {"ProductId": "X1", "LocalizedProperties": ["not-a-dict"], "Properties": None},
        {"ProductId": "X1", "LocalizedProperties": [{"Images": "nope"}], "Properties": "x"},
        {"ProductId": "X1", "LocalizedProperties": [{"DeveloperName": 5}], "Images": None},
    ],
)
def test_parse_product_is_defensive_about_malformed_shapes(product: dict[str, Any]) -> None:
    game = parse_product(product, ["pc"])
    assert game is not None
    assert game.title == "X1"
    assert game.developer is None
    assert game.release_date is None
    assert game.image_url is None
    assert game.categories == ()


def test_parse_product_ignores_root_level_images() -> None:
    product = {
        "ProductId": "X1",
        "LocalizedProperties": [{"ProductTitle": "Title"}],
        "Images": [{"ImagePurpose": "Poster", "Uri": "//img.example.com/root.jpg"}],
    }
    game = parse_product(product, ["pc"])
    assert game is not None
    assert game.image_url is None


def test_parse_product_drops_blank_categories() -> None:
    product = {
        "ProductId": "X1",
        "LocalizedProperties": [{"ProductTitle": "Title"}],
        "Properties": {"Categories": ["Action", "  ", None, 3]},
    }
    game = parse_product(product, ["pc"])
    assert game is not None
    assert game.categories == ("Action",)


def test_parse_product_uses_single_category_when_categories_is_empty() -> None:
    product = {
        "ProductId": "X1",
        "LocalizedProperties": [{"ProductTitle": "Title"}],
        "Properties": {"Categories": [], "Category": "Racing"},
    }
    game = parse_product(product, ["pc"])
    assert game is not None
    assert game.categories == ("Racing",)


# --- fetch_list_ids -------------------------------------------------------------------------


def test_fetch_list_ids_sends_expected_params(
    mock_api: respx.MockRouter, client: httpx.Client, sigl_pc: list[Any]
) -> None:
    route = mock_api.get(CATALOG_URL).mock(return_value=httpx.Response(200, json=sigl_pc))

    ids = fetch_list_ids(client, GAME_LISTS["pc"], "TR", "tr-tr")

    assert ids == PC_IDS
    params = route.calls.last.request.url.params
    assert params["id"] == GAME_LISTS["pc"]
    assert params["market"] == "TR"
    assert params["language"] == "tr-tr"


def test_fetch_list_ids_bad_payload_is_source_error(
    mock_api: respx.MockRouter, client: httpx.Client
) -> None:
    mock_api.get(CATALOG_URL).mock(return_value=httpx.Response(200, json={"error": "nope"}))
    with pytest.raises(SourceError):
        fetch_list_ids(client, GAME_LISTS["pc"], "US", "en-us")


# --- fetch_product_details ------------------------------------------------------------------


def test_fetch_product_details_batches_requests(
    mock_api: respx.MockRouter, client: httpx.Client
) -> None:
    ids = ["ID1", "ID2", "ID3", "ID4", "ID5"]

    def respond(request: httpx.Request) -> httpx.Response:
        requested = request.url.params["bigIds"].split(",")
        return httpx.Response(200, json={"Products": [{"ProductId": i} for i in requested]})

    route = mock_api.get(PRODUCTS_URL).mock(side_effect=respond)

    products = fetch_product_details(client, ids, "gb", "en-gb", batch_size=2)

    assert route.call_count == 3
    sent = [call.request.url.params for call in route.calls]
    assert [p["bigIds"] for p in sent] == ["ID1,ID2", "ID3,ID4", "ID5"]
    assert all(p["market"] == "gb" and p["languages"] == "en-gb" for p in sent)
    assert [p["ProductId"] for p in products] == ids


def test_fetch_product_details_single_batch_when_size_is_large(
    mock_api: respx.MockRouter, client: httpx.Client
) -> None:
    route = mock_api.get(PRODUCTS_URL).mock(return_value=httpx.Response(200, json={"Products": []}))
    fetch_product_details(client, ["A", "B", "C"], "US", "en-us", batch_size=20)
    assert route.call_count == 1


def test_fetch_product_details_no_ids_makes_no_requests(
    client: httpx.Client,
) -> None:
    # Mocked routes would be asserted as called, so use a router that does not assert.
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        route = router.get(PRODUCTS_URL).mock(
            return_value=httpx.Response(200, json={"Products": []})
        )
        assert fetch_product_details(client, [], "US", "en-us", batch_size=20) == []
        assert not route.called


def test_fetch_product_details_ignores_non_dict_entries(
    mock_api: respx.MockRouter, client: httpx.Client
) -> None:
    mock_api.get(PRODUCTS_URL).mock(
        return_value=httpx.Response(200, json={"Products": [{"ProductId": "A"}, "junk", None]})
    )
    assert fetch_product_details(client, ["A"], "US", "en-us", batch_size=20) == [
        {"ProductId": "A"}
    ]


@pytest.mark.parametrize("body", [{"Products": None}, {"Other": []}, {}, [], "text"])
def test_fetch_product_details_bad_payload_is_source_error(
    mock_api: respx.MockRouter, client: httpx.Client, body: object
) -> None:
    mock_api.get(PRODUCTS_URL).mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(SourceError):
        fetch_product_details(client, ["A"], "US", "en-us", batch_size=20)


# --- fetch_games ----------------------------------------------------------------------------


def test_fetch_games_merges_pc_and_console(
    install_microsoft: Any,
    client: httpx.Client,
    displaycatalog_products: dict[str, Any],
) -> None:
    catalog_route, products_route = install_microsoft(
        {
            GAME_LISTS["pc"]: PC_IDS,
            GAME_LISTS["console"]: CONSOLE_IDS,
        },
        displaycatalog_products["Products"],
    )

    games = fetch_games(client, ["pc", "console"], [], "US", "en-us", batch_size=20)

    # Two list requests, one details request covering each unique ID once.
    assert catalog_route.call_count == 2
    assert products_route.call_count == 1
    requested = products_route.calls.last.request.url.params["bigIds"].split(",")
    assert sorted(requested) == sorted(set(PC_IDS) | set(CONSOLE_IDS))
    assert len(requested) == len(set(requested))

    by_id = {game.product_id: game for game in games}
    # 9MZ1SNWT0N5D is console-only, 9N7TCNNW7C7N is missing from the catalog and skipped.
    assert set(by_id) == {
        "9NBLGGH4R315",
        "9PFZWPPG2HZ8",
        "9NZ9Q8N8NC2Z",
        "9P8GB3D2SZ5K",
        "9MZ1SNWT0N5D",
    }
    assert by_id["9NBLGGH4R315"].lists == ("pc",)
    assert by_id["9MZ1SNWT0N5D"].lists == ("console",)
    assert by_id["9NZ9Q8N8NC2Z"].lists == ("console", "pc")  # overlap
    assert by_id["9NZ9Q8N8NC2Z"].release_date is None  # 1601 placeholder

    titles = [game.title for game in games]
    assert titles == sorted(titles, key=str.casefold)


def test_fetch_games_sends_market_and_language(
    install_microsoft: Any,
    client: httpx.Client,
    displaycatalog_products: dict[str, Any],
) -> None:
    catalog_route, products_route = install_microsoft(
        {GAME_LISTS["pc"]: PC_IDS}, displaycatalog_products["Products"]
    )

    fetch_games(client, ["pc"], [], "TR", "tr-tr", batch_size=20)

    for call in catalog_route.calls:
        assert call.request.url.params["market"] == "TR"
        assert call.request.url.params["language"] == "tr-tr"
    assert products_route.calls.last.request.url.params["market"] == "TR"
    assert products_route.calls.last.request.url.params["languages"] == "tr-tr"


def test_fetch_games_labels_extra_sigl_ids(
    install_microsoft: Any,
    client: httpx.Client,
) -> None:
    extra = "11111111-2222-3333-4444-555555555555"
    install_microsoft(
        {extra: ["EXTRA00001"]},
        [{"ProductId": "EXTRA00001", "LocalizedProperties": [{"ProductTitle": "Extra"}]}],
    )

    games = fetch_games(client, [], [extra], "US", "en-us", batch_size=20)

    assert [(g.title, g.lists) for g in games] == [("Extra", (f"sigl:{extra}",))]


def test_fetch_games_list_without_products_returns_empty(
    install_microsoft: Any,
    client: httpx.Client,
) -> None:
    install_microsoft({GAME_LISTS["ea-play"]: ["ORPHAN00001"]}, [])
    assert fetch_games(client, ["ea-play"], [], "US", "en-us", batch_size=20) == []


def test_fetch_games_batch_size_is_respected(
    install_microsoft: Any,
    client: httpx.Client,
) -> None:
    ids = ["P1", "P2", "P3"]
    products = [{"ProductId": pid, "LocalizedProperties": [{"ProductTitle": pid}]} for pid in ids]
    _, products_route = install_microsoft({GAME_LISTS["cloud"]: ids}, products)

    games = fetch_games(client, ["cloud"], [], "US", "en-us", batch_size=1)

    assert products_route.call_count == 3
    assert {g.product_id for g in games} == set(ids)
    assert all(g.source == microsoft.SOURCE_NAME for g in games)
    assert all(isinstance(g, Game) for g in games)
