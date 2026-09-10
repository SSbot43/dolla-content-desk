"""Use deterministic UTF-8 decoding for Git subprocess output on Windows.

Windows Python otherwise decodes subprocess pipes with the active ANSI code page (for example
cp1252). Git can emit UTF-8 filenames/content, which caused reader-thread UnicodeDecodeError
tracebacks during Content Desk queue/sync operations.
"""
from __future__ import annotations

import subprocess


def install(desk) -> None:
    def run_git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(desk.CONTENT_REPO), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=90,
            check=False,
        )

    desk.run_git = run_git
