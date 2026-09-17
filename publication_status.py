"""Read published status independently of the editable local content checkout."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

_CACHE = {}
_LOCK = threading.Lock()
REFRESH_SECONDS = 45


def _git(repo: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=8, check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"},
    )


def dashboard_publications(repo: Path, local: dict) -> tuple[dict, str]:
    """Fetch only refs; never reset, stash, overwrite, or publish local work."""
    key = str(repo.resolve())
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and time.monotonic() - cached[0] < REFRESH_SECONDS:
            return (cached[1] if cached[1] is not None else local), cached[2]
        fresh = False
        try:
            fresh = _git(repo, "fetch", "origin", "refs/heads/main:refs/remotes/origin/main").returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass
        records = None
        try:
            result = _git(repo, "show", "refs/remotes/origin/main:content/published.json")
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if isinstance(data, dict) and all(isinstance(v, dict) for v in data.values()):
                    records = data
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        if records is not None:
            note = "Checked against GitHub publication records." if fresh else "Offline: showing last synced GitHub publication records."
        else:
            note = "Could not check GitHub: showing local publication records, which may be out of date."
        _CACHE[key] = (time.monotonic(), records, note)
        return (records if records is not None else local), note

