"""Safe local bootstrap for Dolla Content Desk.

Python imports sitecustomize automatically at startup. The desk UI and the content engine live in
separate sibling repos, while the user's launcher historically only pulled the desk repo. This
keeps the engine current too, without touching it when local edits are present.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        text=True,
        capture_output=True,
        timeout=25,
        check=False,
    )


def _sync_content_engine() -> None:
    if os.environ.get("DOLLA_SKIP_ENGINE_SYNC", "").strip() == "1":
        return

    desk = Path(__file__).resolve().parent
    engine = Path(os.environ.get("CONTENT_REPO", desk.parent / "dollacasino-content")).resolve()
    if not (engine / ".git").exists():
        return

    try:
        status = _run("git", "-C", str(engine), "status", "--porcelain")
        if status.returncode != 0 or status.stdout.strip():
            # Never overwrite or merge through local engine work.
            return
        _run("git", "-C", str(engine), "pull", "--ff-only", "--quiet")
    except Exception:
        # Startup must never fail just because GitHub/network is unavailable.
        return


_sync_content_engine()
