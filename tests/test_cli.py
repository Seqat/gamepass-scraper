"""Tests for the command-line interface. Every HTTP call is mocked with respx."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from gamepass_scraper import __version__, cli
from gamepass_scraper.export import CSV_FIELDS
from gamepass_scraper.http import make_client
from gamepass_scraper.lists import GAME_LISTS
from gamepass_scraper.sources import gamepasscounter, microsoft
from gamepass_scraper.sources.gamepasscounter import PAGE_URL

PC_IDS = ["9NBLGGH4R315", "9PFZWPPG2HZ8", "9NZ9Q8N8NC2Z", "9P8GB3D2SZ5K"]
CONSOLE_IDS = ["9NZ9Q8N8NC2Z", "9MZ1SNWT0N5D", "9N7TCNNW7C7N"]
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run each test from an empty directory so default output files land there."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _catalog_failure(mock_api: respx.MockRouter) -> respx.Route:
    return mock_api.get(microsoft.CATALOG_URL).mock(return_value=httpx.Response(500))


# --- parser ---------------------------------------------------------------------------------


def test_parser_defaults() -> None:
    args = cli.build_parser().parse_args([])
    assert args.lists is None
    assert args.sigl_ids == []
    assert args.market == "US"
    assert args.language == "en-us"
    assert args.source == "auto"
    assert args.format == "csv"
    assert args.output is None
    assert args.timeout == 20.0
    assert args.batch_size == 20
    assert args.quiet is False
    assert args.verbose is False


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        cli.main(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.strip() == f"gamepass-scraper {__version__}"


def test_python_m_entry_point_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "gamepass_scraper", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert __version__ in result.stdout


@pytest.mark.parametrize(
    "argv",
    [
        ["--list", "bogus"],
        ["--source", "gamepasscounter", "--list", "console"],
        ["--source", "gamepasscounter", "--list", "all"],
        ["--source", "gamepasscounter", "--sigl-id", "EXTRA"],
        ["--batch-size", "0"],
        ["--batch-size", "many"],
        ["--timeout", "-1"],
        ["--timeout", "0"],
        ["--timeout", "nan"],
        ["--format", "xml"],
        ["--source", "ftp"],
        ["--quiet", "--verbose"],
        ["--market"],
        ["--unknown-flag"],
    ],
)
def test_usage_errors_exit_with_code_2(argv: list[str], workdir: Path) -> None:
    # No HTTP mocks are installed: a usage error must be reported before any request.
    with pytest.raises(SystemExit) as info:
        cli.main(argv)
    assert info.value.code == 2


# --- happy paths ----------------------------------------------------------------------------


def test_default_run_exports_pc_csv(
    workdir: Path, install_microsoft: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog, _ = install_microsoft({GAME_LISTS["pc"]: PC_IDS})

    assert cli.main([]) == 0

    assert catalog.call_count == 1
    assert catalog.calls.last.request.url.params["id"] == GAME_LISTS["pc"]
    output = workdir / "games.csv"
    with output.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == CSV_FIELDS
    assert len(rows) == 4
    assert {row["source"] for row in rows} == {"microsoft"}
    err = capsys.readouterr().err
    assert "INFO: Found 4 games (lists: pc) via microsoft -> games.csv" in err


def test_json_format_defaults_to_games_json(workdir: Path, install_microsoft: Any) -> None:
    install_microsoft({GAME_LISTS["pc"]: PC_IDS})

    assert cli.main(["--format", "json"]) == 0

    data = json.loads((workdir / "games.json").read_text(encoding="utf-8"))
    assert len(data) == 4


def test_json_to_stdout_is_pure_json(
    workdir: Path, install_microsoft: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    install_microsoft({GAME_LISTS["pc"]: PC_IDS})

    assert cli.main(["--list", "pc", "--format", "json", "-o", "-"]) == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)  # stdout must contain only the JSON document
    assert {game["title"] for game in data} >= {"Pixel Harbor"}
    assert "Found 4 games" in captured.err
    assert "-> stdout" in captured.err


def test_list_all_expands_every_list_in_order(workdir: Path, install_microsoft: Any) -> None:
    catalog, _ = install_microsoft(
        {
            GAME_LISTS["pc"]: PC_IDS,
            GAME_LISTS["console"]: CONSOLE_IDS,
            GAME_LISTS["cloud"]: ["CLOUD000001"],
            GAME_LISTS["ea-play"]: ["EAPLAY00001"],
        }
    )

    # "pc" is repeated and must only be requested once, keeping its first position.
    assert cli.main(["--list", "pc", "--list", "all", "-o", "out.csv"]) == 0

    requested = [call.request.url.params["id"] for call in catalog.calls]
    assert requested == list(GAME_LISTS.values())


def test_sigl_id_alone_requests_only_extra_list(
    workdir: Path, install_microsoft: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    extra = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
    catalog, _ = install_microsoft({extra: ["9MZ1SNWT0N5D"]})

    assert cli.main(["--sigl-id", extra, "-o", "-"]) == 0

    assert [call.request.url.params["id"] for call in catalog.calls] == [extra]
    assert "lists: sigl:" + extra in capsys.readouterr().err


def test_market_and_language_are_normalised(workdir: Path, install_microsoft: Any) -> None:
    catalog, products = install_microsoft({GAME_LISTS["pc"]: PC_IDS})

    assert cli.main(["--market", "tr", "--language", "TR-TR", "-o", "out.csv"]) == 0

    params = catalog.calls.last.request.url.params
    assert params["market"] == "TR"
    assert params["language"] == "tr-tr"
    assert products.calls.last.request.url.params["languages"] == "tr-tr"


def test_batch_size_controls_detail_requests(workdir: Path, install_microsoft: Any) -> None:
    _, products = install_microsoft({GAME_LISTS["pc"]: PC_IDS})

    assert cli.main(["--batch-size", "2", "-o", "out.csv"]) == 0

    # Four unique IDs in batches of two.
    assert products.call_count == 2


def test_quiet_suppresses_summary(
    workdir: Path, install_microsoft: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    install_microsoft({GAME_LISTS["pc"]: PC_IDS})
    assert cli.main(["-q", "-o", "out.csv"]) == 0
    assert "Found" not in capsys.readouterr().err


def test_verbose_shows_debug_messages(
    workdir: Path, install_microsoft: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    install_microsoft({GAME_LISTS["pc"]: PC_IDS})
    assert cli.main(["-v", "-o", "out.csv"]) == 0
    assert "DEBUG: List pc contains 4 product IDs" in capsys.readouterr().err


# --- errors and exit codes ------------------------------------------------------------------


def test_microsoft_failure_with_source_microsoft_exits_1(
    workdir: Path, mock_api: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_api.get(microsoft.CATALOG_URL).mock(return_value=httpx.Response(404))

    assert cli.main(["--source", "microsoft", "-o", "out.csv"]) == 1

    assert "ERROR: HTTP 404" in capsys.readouterr().err
    assert not (workdir / "out.csv").exists()


@pytest.mark.parametrize("failure", ["http-500", "bad-payload"])
def test_auto_falls_back_to_gamepasscounter_for_pc(
    workdir: Path,
    mock_api: respx.MockRouter,
    gamepasscounter_html: str,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    if failure == "http-500":
        mock_api.get(microsoft.CATALOG_URL).mock(return_value=httpx.Response(500))
    else:
        mock_api.get(microsoft.CATALOG_URL).mock(
            return_value=httpx.Response(200, json={"unexpected": True})
        )
    mock_api.get(PAGE_URL).mock(return_value=httpx.Response(200, text=gamepasscounter_html))

    assert cli.main(["-o", "out.csv"]) == 0

    err = capsys.readouterr().err
    assert "falling back to gamepasscounter.com" in err
    assert "via gamepasscounter -> out.csv" in err
    with (workdir / "out.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [row["title"] for row in rows] == ["Pixel Harbor", "Quiet Fjord", "Ember & Ash"]
    assert {row["source"] for row in rows} == {"gamepasscounter"}


def test_no_fallback_when_console_is_requested(
    workdir: Path, gamepasscounter_html: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with respx.mock(assert_all_called=False) as router:
        _catalog_failure(router)
        page = router.get(PAGE_URL).mock(
            return_value=httpx.Response(200, text=gamepasscounter_html)
        )

        assert cli.main(["--list", "pc", "--list", "console", "-o", "out.csv"]) == 1

        assert not page.called
    assert "ERROR: giving up on" in capsys.readouterr().err
    assert not (workdir / "out.csv").exists()


@pytest.mark.parametrize("argv", [["--sigl-id", "EXTRA-LIST"], ["--list", "pc", "--sigl-id", "X"]])
def test_no_fallback_when_extra_sigl_ids_are_given(
    workdir: Path, gamepasscounter_html: str, argv: list[str]
) -> None:
    with respx.mock(assert_all_called=False) as router:
        _catalog_failure(router)
        page = router.get(PAGE_URL).mock(
            return_value=httpx.Response(200, text=gamepasscounter_html)
        )

        assert cli.main([*argv, "-o", "out.csv"]) == 1

        assert not page.called


def test_no_fallback_when_microsoft_succeeds(
    workdir: Path, install_microsoft: Any, gamepasscounter_html: str
) -> None:
    install_microsoft({GAME_LISTS["pc"]: PC_IDS})
    with respx.mock(assert_all_called=False) as router:
        page = router.get(PAGE_URL).mock(
            return_value=httpx.Response(200, text=gamepasscounter_html)
        )
        assert cli.main(["-o", "out.csv"]) == 0
        assert not page.called


def test_source_gamepasscounter_skips_microsoft(
    workdir: Path, gamepasscounter_html: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with respx.mock(assert_all_called=False) as router:
        catalog = router.get(microsoft.CATALOG_URL).mock(return_value=httpx.Response(200, json=[]))
        page = router.get(PAGE_URL).mock(
            return_value=httpx.Response(200, text=gamepasscounter_html)
        )

        assert cli.main(["--source", "gamepasscounter", "-o", "out.csv"]) == 0

        assert not catalog.called
        assert page.call_count == 1
    assert "via gamepasscounter" in capsys.readouterr().err
    assert gamepasscounter.SOURCE_NAME == "gamepasscounter"


def test_unwritable_output_exits_1(
    workdir: Path,
    mock_api: respx.MockRouter,
    gamepasscounter_html: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock_api.get(PAGE_URL).mock(return_value=httpx.Response(200, text=gamepasscounter_html))
    blocker = workdir / "blocker"
    blocker.write_text("this is a file, not a directory", encoding="utf-8")

    assert cli.main(["--source", "gamepasscounter", "-o", str(blocker / "games.csv")]) == 1

    assert "could not write output" in capsys.readouterr().err


def test_keyboard_interrupt_exits_130(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupted(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(microsoft, "fetch_games", interrupted)

    assert cli.main(["-o", "out.csv"]) == 130

    assert "interrupted" in capsys.readouterr().err


def test_make_client_is_used_with_timeout(
    workdir: Path, install_microsoft: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[float] = []

    def spy(timeout: float) -> httpx.Client:
        seen.append(timeout)
        return make_client(timeout)

    install_microsoft({GAME_LISTS["pc"]: PC_IDS})
    monkeypatch.setattr(cli, "make_client", spy)

    assert cli.main(["--timeout", "3.5", "-o", "out.csv"]) == 0
    assert seen == [3.5]
