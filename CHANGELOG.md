# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-08

### Added

- Installable package and `gamepass-scraper` command-line tool (also available as `python -m gamepass_scraper`).
- Microsoft Game Pass catalog as the primary data source (SIGL lists and Store product details).
- Multiple lists in one run with `--list {pc,console,cloud,ea-play,all}` and custom lists with `--sigl-id`. Games that appear in several lists are merged into one row.
- `--market` and `--language` options.
- JSON output with `--format json`, and `-o -` to write to stdout.
- gamepasscounter.com as a fallback source (`--source gamepasscounter`, or automatically in `auto` mode for the PC list).
- Request timeouts, and retries with backoff for transport errors and HTTP 429/5xx responses.
- Test suite with mocked HTTP and recorded fixtures.
- GitHub Actions CI and Dependabot configuration.

### Changed

- HTTP requests and HTML parsing moved from `requests-html` to `httpx` and `lxml`.
- Requires Python 3.11 or newer.
- CSV output includes a header row and is written with `newline=""`.
- The legacy `scraper.py` is now a thin wrapper around the package CLI.

### Removed

- `requirements.txt`, replaced by `pyproject.toml` and `uv.lock`.
- `requests-html` and its `pyppeteer` dependency, which were not used for rendering.

### Fixed

- Import crash with `lxml>=5.2`, where `lxml.html.clean` moved to a separate project.
- `IndexError` when a source returned no games. A clear error is now reported instead.
- Blank and whitespace-only lines were counted as games.
- Requests had no timeout.

## [0.1.0] - 2022-06-25

### Added

- Initial release: a single-file scraper that reads the PC list from gamepasscounter.com and writes `games.csv`.
