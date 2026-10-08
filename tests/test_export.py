"""Tests for CSV and JSON output."""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from gamepass_scraper.export import CSV_FIELDS, write_csv, write_games, write_json
from gamepass_scraper.models import Game

SAMPLE_GAMES = [
    Game(
        title="Pixel Harbor",
        product_id="9NBLGGH4R315",
        developer="Lumen Studio",
        publisher="Lumen Interactive",
        release_date=date(2020, 11, 10),
        categories=("Action", "Indie"),
        image_url="https://img.example.com/poster.jpg",
        lists=("console", "pc"),
        source="microsoft",
    ),
    Game(title='Bare, "quoted" title', lists=("pc",), source="gamepasscounter"),
]


def _csv_text(games: list[Game]) -> str:
    buffer = io.StringIO(newline="")
    write_csv(games, buffer)
    return buffer.getvalue()


def test_csv_fields_are_stable() -> None:
    assert CSV_FIELDS == [
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


def test_csv_header_row() -> None:
    text = _csv_text([])
    assert text.splitlines() == [",".join(CSV_FIELDS)]


def test_csv_rows_join_multi_values_with_semicolon_space() -> None:
    rows = list(csv.reader(io.StringIO(_csv_text(SAMPLE_GAMES))))
    header, first = rows[0], rows[1]
    record = dict(zip(header, first, strict=True))

    assert record["product_id"] == "9NBLGGH4R315"
    assert record["release_date"] == "2020-11-10"
    assert record["categories"] == "Action; Indie"
    assert record["lists"] == "console; pc"
    assert record["source"] == "microsoft"


def test_csv_missing_optional_fields_are_empty_strings() -> None:
    rows = list(csv.reader(io.StringIO(_csv_text(SAMPLE_GAMES))))
    record = dict(zip(rows[0], rows[2], strict=True))

    assert record["title"] == 'Bare, "quoted" title'  # comma and quotes survive quoting
    assert record["product_id"] == ""
    assert record["developer"] == ""
    assert record["release_date"] == ""
    assert record["categories"] == ""
    assert record["image_url"] == ""


def test_csv_has_no_blank_lines() -> None:
    text = _csv_text(SAMPLE_GAMES)
    lines = text.splitlines()
    assert len(lines) == 3  # header + two games
    assert all(line.strip() for line in lines)
    assert "\n\n" not in text.replace("\r\n", "\n")


def test_csv_round_trips_unicode() -> None:
    game = Game(title="Pokémon İstanbul", lists=("pc",))
    rows = list(csv.reader(io.StringIO(_csv_text([game]))))
    assert rows[1][1] == "Pokémon İstanbul"


def test_json_round_trip() -> None:
    buffer = io.StringIO()
    write_json(SAMPLE_GAMES, buffer)
    data = json.loads(buffer.getvalue())
    assert data == [game.to_dict() for game in SAMPLE_GAMES]
    assert data[1]["release_date"] is None


def test_json_format_is_indented_utf8_with_trailing_newline() -> None:
    buffer = io.StringIO()
    write_json([Game(title="Pokémon", lists=("pc",))], buffer)
    text = buffer.getvalue()
    assert text.endswith("]\n")
    assert text.startswith('[\n  {\n    "product_id": null')
    assert "Pokémon" in text  # ensure_ascii=False keeps the character as-is


def test_json_empty_list() -> None:
    buffer = io.StringIO()
    write_json([], buffer)
    assert buffer.getvalue() == "[]\n"


def test_write_games_creates_parent_directories_for_csv(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "games.csv"

    write_games(SAMPLE_GAMES, "csv", str(target))

    assert target.is_file()
    with target.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == CSV_FIELDS
    assert len(rows) == 3


def test_write_games_creates_parent_directories_for_json(tmp_path: Path) -> None:
    target = tmp_path / "out" / "games.json"

    write_games(SAMPLE_GAMES, "json", str(target))

    assert json.loads(target.read_text(encoding="utf-8"))[0]["title"] == "Pixel Harbor"


def test_write_games_dash_writes_csv_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    write_games(SAMPLE_GAMES, "csv", "-")
    out = capsys.readouterr().out
    assert out.splitlines()[0] == ",".join(CSV_FIELDS)
    assert len(out.splitlines()) == 3


def test_write_games_dash_writes_json_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    write_games(SAMPLE_GAMES, "json", "-")
    assert json.loads(capsys.readouterr().out) == [game.to_dict() for game in SAMPLE_GAMES]


def test_csv_to_stdout_has_no_doubled_carriage_returns() -> None:
    """Regression guard for Windows: text-mode stdout turns CRLF into CRCRLF.

    Runs in a child process so the real ``sys.stdout`` is exercised (pytest's capture
    replaces it with a stream that does no newline translation).
    """
    code = (
        "from gamepass_scraper.export import write_games\n"
        "from gamepass_scraper.models import Game\n"
        "write_games([Game(title='A', lists=('pc',)), Game(title='B')], 'csv', '-')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        timeout=120,
        check=True,
    )
    assert b"\r\r" not in result.stdout
    lines = result.stdout.splitlines()
    assert len(lines) == 3
    assert all(lines)


def test_stdout_output_is_utf8_even_under_legacy_locale_encoding() -> None:
    code = (
        "from gamepass_scraper.export import write_games\n"
        "from gamepass_scraper.models import Game\n"
        "write_games([Game(title='\u0130stanbul', lists=('pc',))], 'csv', '-')\n"
    )
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "\u0130stanbul".encode() in result.stdout
