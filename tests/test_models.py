"""Tests for the Game model and merge_games."""

from __future__ import annotations

import dataclasses
import json
from datetime import date

import pytest

from gamepass_scraper.models import Game, merge_games


def test_game_defaults() -> None:
    game = Game(title="Pixel Harbor")
    assert game.product_id is None
    assert game.developer is None
    assert game.publisher is None
    assert game.release_date is None
    assert game.categories == ()
    assert game.image_url is None
    assert game.lists == ()
    assert game.source == "microsoft"


def test_game_is_frozen() -> None:
    game = Game(title="Pixel Harbor")
    with pytest.raises(dataclasses.FrozenInstanceError):
        game.title = "Other"  # type: ignore[misc]


def test_to_dict_full_game() -> None:
    game = Game(
        title="Pixel Harbor",
        product_id="9NBLGGH4R315",
        developer="Lumen Studio",
        publisher="Lumen Interactive",
        release_date=date(2020, 11, 10),
        categories=("Action", "Indie"),
        image_url="https://img.example.com/poster.jpg",
        lists=("console", "pc"),
        source="microsoft",
    )
    assert game.to_dict() == {
        "product_id": "9NBLGGH4R315",
        "title": "Pixel Harbor",
        "developer": "Lumen Studio",
        "publisher": "Lumen Interactive",
        "release_date": "2020-11-10",
        "categories": ["Action", "Indie"],
        "image_url": "https://img.example.com/poster.jpg",
        "lists": ["console", "pc"],
        "source": "microsoft",
    }


def test_to_dict_empty_optional_fields_are_none_or_empty() -> None:
    data = Game(title="Bare").to_dict()
    assert data["product_id"] is None
    assert data["release_date"] is None
    assert data["categories"] == []
    assert data["lists"] == []
    assert data["image_url"] is None


def test_to_dict_is_json_serialisable() -> None:
    game = Game(title="Dated", release_date=date(2021, 3, 2), categories=("RPG",))
    assert json.loads(json.dumps(game.to_dict()))["release_date"] == "2021-03-02"


def test_merge_empty_input_returns_empty_list() -> None:
    assert merge_games([]) == []


def test_merge_unions_lists_for_same_product_id() -> None:
    pc = Game(title="Pixel Harbor", product_id="ID1", lists=("pc",), source="microsoft")
    console = Game(title="Pixel Harbor", product_id="ID1", lists=("console",))

    merged = merge_games([pc, console])

    assert len(merged) == 1
    assert merged[0].lists == ("console", "pc")


def test_merge_lists_are_sorted_and_unique_even_for_single_game() -> None:
    game = Game(title="Solo", product_id="ID1", lists=("pc", "console", "pc"))
    assert merge_games([game])[0].lists == ("console", "pc")


def test_merge_keeps_first_non_empty_fields() -> None:
    first = Game(title="Pixel Harbor", product_id="ID1", developer=None, publisher="Pub A")
    second = Game(
        title="Pixel Harbor",
        product_id="ID1",
        developer="Dev B",
        publisher="Pub B",
        release_date=date(2020, 1, 1),
        categories=("Action",),
        image_url="https://img.example.com/a.jpg",
    )

    (merged,) = merge_games([first, second])

    assert merged.developer == "Dev B"  # first was empty, so second fills it
    assert merged.publisher == "Pub A"  # first wins when both are set
    assert merged.release_date == date(2020, 1, 1)
    assert merged.categories == ("Action",)
    assert merged.image_url == "https://img.example.com/a.jpg"


def test_merge_first_occurrence_wins_over_later_values() -> None:
    first = Game(title="Title One", product_id="ID1", developer="First")
    second = Game(title="Title Two", product_id="ID1", developer="Second")

    (merged,) = merge_games([first, second])

    assert merged.title == "Title One"
    assert merged.developer == "First"


def test_merge_without_product_id_uses_casefolded_title() -> None:
    upper = Game(title="HALO", lists=("pc",))
    lower = Game(title="halo", lists=("console",), developer="Dev")

    merged = merge_games([upper, lower])

    assert len(merged) == 1
    assert merged[0].title == "HALO"
    assert merged[0].developer == "Dev"
    assert merged[0].lists == ("console", "pc")


def test_merge_keeps_same_title_with_different_product_ids_apart() -> None:
    first = Game(title="Remaster", product_id="ID1")
    second = Game(title="Remaster", product_id="ID2")
    assert len(merge_games([first, second])) == 2


def test_merge_does_not_join_title_only_game_with_product_id_game() -> None:
    with_id = Game(title="Same Title", product_id="ID1")
    without_id = Game(title="Same Title")
    assert len(merge_games([with_id, without_id])) == 2


def test_merge_sorts_by_casefolded_title() -> None:
    games = [
        Game(title="cherry", product_id="3"),
        Game(title="Apple", product_id="1"),
        Game(title="banana", product_id="2"),
    ]
    assert [g.title for g in merge_games(games)] == ["Apple", "banana", "cherry"]


def test_merge_does_not_mutate_inputs() -> None:
    original = Game(title="Pixel Harbor", product_id="ID1", lists=("pc",))
    merge_games([original, Game(title="Pixel Harbor", product_id="ID1", lists=("console",))])
    assert original.lists == ("pc",)
