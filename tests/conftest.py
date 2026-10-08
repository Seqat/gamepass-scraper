"""Shared fixtures: fixture-file loaders, a mocked HTTP router and a no-op retry sleep."""

from __future__ import annotations

import json
import socket
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from gamepass_scraper import http as http_module
from gamepass_scraper.http import make_client
from gamepass_scraper.sources import microsoft

FIXTURES_DIR = Path(__file__).parent / "fixtures"

MicrosoftInstaller = Callable[..., tuple[respx.Route, respx.Route]]


def load_json(name: str) -> Any:
    """Load a JSON file from ``tests/fixtures``."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def load_text(name: str) -> str:
    """Load a text file from ``tests/fixtures``."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest.fixture
def sigl_pc() -> list[Any]:
    """Raw SIGL response for the PC list (metadata first, duplicate ID included)."""
    return load_json("sigl_pc.json")


@pytest.fixture
def sigl_console() -> list[Any]:
    """Raw SIGL response for the console list (partially overlaps the PC list)."""
    return load_json("sigl_console.json")


@pytest.fixture
def displaycatalog_products() -> dict[str, Any]:
    """Raw display-catalog response with edge-case products."""
    return load_json("displaycatalog_products.json")


@pytest.fixture
def gamepasscounter_html() -> str:
    """Minimal gamepasscounter.com page containing the legacy list markup."""
    return load_text("gamepasscounter.html")


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    """A real client built by ``make_client``; all requests go through respx."""
    with make_client(timeout=5.0) as http_client:
        yield http_client


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    """Route-mocking router. Every route must be called, and unmocked requests fail."""
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as router:
        yield router


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if any test opens a real socket, even when a request is not mocked."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("tests must not open network connections; mock the request with respx")

    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture(autouse=True)
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace retry sleeps with a recorder so tests never wait."""
    recorded: list[float] = []
    monkeypatch.setattr(http_module, "_sleep", recorded.append)
    return recorded


@pytest.fixture
def install_microsoft(mock_api: respx.MockRouter) -> MicrosoftInstaller:
    """Register mock routes for the SIGL and display-catalog endpoints.

    ``lists`` maps each SIGL ID to the product IDs it contains. Unknown SIGL IDs get a 404.
    ``products`` are the raw display-catalog records to return; requested IDs that are not in
    ``products`` are simply absent from the response. Returns the (catalog, products) routes.
    """

    def install(
        lists: Mapping[str, Sequence[str]],
        products: Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[respx.Route, respx.Route]:
        records: Sequence[Mapping[str, Any]] = (
            products
            if products is not None
            else load_json("displaycatalog_products.json")["Products"]
        )
        by_id = {str(product["ProductId"]): product for product in records}

        def catalog(request: httpx.Request) -> httpx.Response:
            sigl_id = request.url.params.get("id", "")
            if sigl_id not in lists:
                return httpx.Response(404, json={"error": "unknown list"})
            body: list[dict[str, str]] = [{"siglId": sigl_id, "title": "fixture list"}]
            body.extend({"id": product_id} for product_id in lists[sigl_id])
            return httpx.Response(200, json=body)

        def details(request: httpx.Request) -> httpx.Response:
            requested = request.url.params.get("bigIds", "").split(",")
            found = [by_id[pid] for pid in requested if pid in by_id]
            return httpx.Response(200, json={"Products": found})

        catalog_route = mock_api.get(microsoft.CATALOG_URL).mock(side_effect=catalog)
        products_route = mock_api.get(microsoft.PRODUCTS_URL).mock(side_effect=details)
        return catalog_route, products_route

    return install
