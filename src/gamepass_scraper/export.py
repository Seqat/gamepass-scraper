"""Write games to CSV or JSON."""

from __future__ import annotations

import csv
import io
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, TextIO

from gamepass_scraper.models import Game

CSV_FIELDS = [
    "product_id",
    "title",
    "developer",
    "publisher",
    "release_date",
    "categories",
    "image_url",
    "lists",
    "source",
]


def write_csv(games: Sequence[Game], fh: TextIO) -> None:
    """Write a header row followed by one row per game.

    The stream should be opened with ``newline=""`` and UTF-8 encoding.
    """
    writer = csv.writer(fh)
    writer.writerow(CSV_FIELDS)
    for game in games:
        writer.writerow(
            [
                game.product_id or "",
                game.title,
                game.developer or "",
                game.publisher or "",
                game.release_date.isoformat() if game.release_date else "",
                "; ".join(game.categories),
                game.image_url or "",
                "; ".join(game.lists),
                game.source,
            ]
        )


def write_json(games: Sequence[Game], fh: TextIO) -> None:
    """Write games as a JSON array with a trailing newline."""
    json.dump([game.to_dict() for game in games], fh, ensure_ascii=False, indent=2)
    fh.write("\n")


def write_games(games: Sequence[Game], fmt: Literal["csv", "json"], output: str) -> None:
    """Write games to ``output`` (a file path, or ``-`` for stdout).

    Parent directories of the output file are created as needed.
    """
    if output == "-":
        if fmt == "csv" and isinstance(sys.stdout, io.TextIOWrapper):
            # The csv module writes its own \r\n; stop text mode turning it into \r\r\n.
            sys.stdout.reconfigure(newline="")
        _write_stream(games, fmt, sys.stdout)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        _write_stream(games, fmt, fh)


def _write_stream(games: Sequence[Game], fmt: Literal["csv", "json"], fh: TextIO) -> None:
    if fmt == "csv":
        write_csv(games, fh)
    else:
        write_json(games, fh)
