"""Backward-compatible launcher for the Dolla Content Desk Flask app.

All routes live in app.py so importing or running the app directly has the complete workflow.
This launcher also keeps the local content repo in sync with GitHub while the desk is open.
It only pulls when the content repo has no local/uncommitted changes, so it will never overwrite
an article, image, or queue change that is still waiting on this PC.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

import app as desk
from immediate_publish import install as install_publish_policy
from manual_override import install as install_manual_override
from review_state_fix import install as install_review_state_fix
from encoding_git import install as install_encoding_git
from resilient_git import install as install_resilient_git

install_publish_policy(desk)
install_manual_override(desk)
install_review_state_fix(desk)
install_encoding_git(desk)
install_resilient_git(desk)
app = desk.app

SYNC_SECONDS = int(os.environ.get("CONTENT_SYNC_SECONDS", "45"))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )


def _sync_content_repo_once(repo: Path) -> None:
    """Fast-forward the content repo only when doing so cannot disturb local work."""
    if not (repo / ".git").exists():
        return

    status = _git(repo, "status", "--porcelain")
    if status.returncode != 0 or status.stdout.strip():
        # Local queue/image/article work exists. Leave it alone until the user pushes it.
        return

    # Fetch first so a remote scheduled publish becomes visible locally. --ff-only guarantees
    # we never rewrite local history if another PC has made a commit meanwhile.
    fetch = _git(repo, "fetch", "origin", "main")
    if fetch.returncode != 0:
        return
    _git(repo, "pull", "--ff-only", "origin", "main")


def _sync_loop(repo: Path) -> None:
    # Give Flask a moment to start, then keep checking quietly in the background.
    time.sleep(2)
    while True:
        try:
            _sync_content_repo_once(repo)
        except Exception:
            # Sync is convenience only; never take the local Content Desk down over Git/network.
            pass
        time.sleep(max(15, SYNC_SECONDS))


if __name__ == "__main__":
    content_repo = Path(os.environ.get("CONTENT_REPO", str(desk.CONTENT_REPO))).resolve()
    threading.Thread(target=_sync_loop, args=(content_repo,), daemon=True).start()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True, use_reloader=False)
