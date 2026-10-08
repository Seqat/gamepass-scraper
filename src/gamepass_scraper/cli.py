"""Command-line interface for gamepass-scraper."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

import httpx

from gamepass_scraper import __version__
from gamepass_scraper.errors import ScraperError
from gamepass_scraper.export import write_games
from gamepass_scraper.http import make_client
from gamepass_scraper.lists import GAME_LISTS
from gamepass_scraper.models import Game
from gamepass_scraper.sources import gamepasscounter, microsoft

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERRUPTED = 130
DEFAULT_LIST = "pc"
FALLBACK_LIST = "pc"
LIST_CHOICES = [*GAME_LISTS, "all"]


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="gamepass-scraper",
        description="Export the Xbox Game Pass game catalog to CSV or JSON.",
    )
    parser.add_argument(
        "--list",
        dest="lists",
        action="append",
        choices=LIST_CHOICES,
        metavar="{" + ",".join(LIST_CHOICES) + "}",
        help="Game Pass list to export (repeatable; 'all' selects every list). "
        f"Default: {DEFAULT_LIST} when no --sigl-id is given.",
    )
    parser.add_argument(
        "--sigl-id",
        dest="sigl_ids",
        action="append",
        default=[],
        metavar="ID",
        help="Extra Microsoft SIGL list ID to export (repeatable).",
    )
    parser.add_argument("--market", default="US", help="Catalog market code (default: US).")
    parser.add_argument(
        "--language", default="en-us", help="Catalog language tag (default: en-us)."
    )
    parser.add_argument(
        "--source",
        choices=["auto", "microsoft", "gamepasscounter"],
        default="auto",
        help="Data source. 'auto' falls back to gamepasscounter.com for PC-only exports "
        "when Microsoft is unavailable (default: auto).",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Output format (default: csv).",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="Output file, or '-' for stdout (default: games.csv or games.json).",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=20.0,
        metavar="SECONDS",
        help="HTTP timeout in seconds (default: 20).",
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=20,
        metavar="N",
        help="Product IDs per details request (default: 20).",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-q", "--quiet", action="store_true", help="Only show warnings and errors."
    )
    verbosity.add_argument("-v", "--verbose", action="store_true", help="Show debug output.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(quiet=args.quiet, verbose=args.verbose)

    lists = _resolve_lists(args.lists, args.sigl_ids)
    if args.source == "gamepasscounter" and (set(lists) != {FALLBACK_LIST} or args.sigl_ids):
        parser.error("--source gamepasscounter only supports --list pc (without --sigl-id)")

    market = args.market.upper()
    language = args.language.lower()
    output = args.output or f"games.{args.format}"

    try:
        with make_client(args.timeout) as client:
            games, used_source = _fetch(
                client,
                args.source,
                lists,
                args.sigl_ids,
                market=market,
                language=language,
                batch_size=args.batch_size,
            )
        write_games(games, args.format, output)
    except ScraperError as exc:
        logger.error("%s", exc)
        return EXIT_ERROR
    except httpx.HTTPError as exc:
        logger.error("network error: %s", exc)
        return EXIT_ERROR
    except OSError as exc:
        logger.error("could not write output: %s", exc)
        return EXIT_ERROR
    except KeyboardInterrupt:
        logger.error("interrupted")
        return EXIT_INTERRUPTED

    label = ", ".join([*lists, *(f"sigl:{sigl_id}" for sigl_id in args.sigl_ids)])
    destination = "stdout" if output == "-" else output
    logger.info(
        "Found %d games (lists: %s) via %s -> %s",
        len(games),
        label,
        used_source,
        destination,
    )
    return EXIT_OK


def _fetch(
    client: httpx.Client,
    source: str,
    lists: list[str],
    sigl_ids: Sequence[str],
    *,
    market: str,
    language: str,
    batch_size: int,
) -> tuple[list[Game], str]:
    """Fetch games from the requested source, applying the auto fallback rule."""
    if source in ("auto", "microsoft"):
        try:
            games = microsoft.fetch_games(
                client, lists, list(sigl_ids), market, language, batch_size
            )
            return games, microsoft.SOURCE_NAME
        except ScraperError as exc:
            fallback_allowed = set(lists) == {FALLBACK_LIST} and not sigl_ids
            if source == "microsoft" or not fallback_allowed:
                raise
            logger.warning(
                "Microsoft catalog failed (%s); falling back to gamepasscounter.com", exc
            )
    return gamepasscounter.fetch_games(client), gamepasscounter.SOURCE_NAME


def _resolve_lists(requested: Sequence[str] | None, sigl_ids: Sequence[str]) -> list[str]:
    """Expand ``all`` and apply the default list, keeping order and removing duplicates."""
    if not requested:
        return [] if sigl_ids else [DEFAULT_LIST]
    names: list[str] = []
    for name in requested:
        expanded = list(GAME_LISTS) if name == "all" else [name]
        for item in expanded:
            if item not in names:
                names.append(item)
    return names


def _configure_logging(*, quiet: bool, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )
    # httpx logs every request at INFO, which is noise for this tool's default output.
    logging.getLogger("httpx").setLevel(logging.DEBUG if verbose else logging.WARNING)


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {text!r}") from exc
    if value < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {text!r}")
    return value


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a positive number, got {text!r}") from exc
    if not value > 0:
        raise argparse.ArgumentTypeError(f"expected a positive number, got {text!r}")
    return value
