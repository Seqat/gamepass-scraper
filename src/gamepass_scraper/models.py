"""Data model for catalog entries and helpers to combine them."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class Game:
    """A single Game Pass title."""

    title: str
    product_id: str | None = None
    developer: str | None = None
    publisher: str | None = None
    release_date: date | None = None
    categories: tuple[str, ...] = ()
    image_url: str | None = None
    lists: tuple[str, ...] = ()
    source: str = "microsoft"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of this game."""
        return {
            "product_id": self.product_id,
            "title": self.title,
            "developer": self.developer,
            "publisher": self.publisher,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "categories": list(self.categories),
            "image_url": self.image_url,
            "lists": list(self.lists),
            "source": self.source,
        }


def merge_games(games: Iterable[Game]) -> list[Game]:
    """Combine duplicate games and return them sorted by title.

    Games are identified by ``product_id``; games without one are identified by their
    casefolded title. For duplicates, ``lists`` becomes the sorted union and every other
    field keeps the first non-empty value seen.
    """
    merged: dict[str, Game] = {}
    for game in games:
        key = _merge_key(game)
        existing = merged.get(key)
        merged[key] = _normalized(game) if existing is None else _merge_pair(existing, game)
    return sorted(merged.values(), key=_sort_key)


def _merge_key(game: Game) -> str:
    if game.product_id:
        return f"id:{game.product_id}"
    return f"title:{game.title.casefold()}"


def _sort_key(game: Game) -> tuple[str, str, str]:
    return (game.title.casefold(), game.product_id or "", game.title)


def _normalized(game: Game) -> Game:
    return replace(game, lists=tuple(sorted(set(game.lists))))


def _merge_pair(first: Game, second: Game) -> Game:
    return Game(
        title=first.title or second.title,
        product_id=first.product_id or second.product_id,
        developer=first.developer or second.developer,
        publisher=first.publisher or second.publisher,
        release_date=first.release_date or second.release_date,
        categories=first.categories or second.categories,
        image_url=first.image_url or second.image_url,
        lists=tuple(sorted(set(first.lists) | set(second.lists))),
        source=first.source or second.source,
    )
