"""Legacy entry point: ``python scraper.py`` behaves like the ``gamepass-scraper`` command.

Works both when the package is installed and when run from a fresh clone without install.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from gamepass_scraper.cli import main
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from gamepass_scraper.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
