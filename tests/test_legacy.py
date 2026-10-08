"""The legacy ``scraper.py`` entry point must keep working."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_legacy_script_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scraper.py"), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage: gamepass-scraper" in result.stdout
    assert "--source" in result.stdout
