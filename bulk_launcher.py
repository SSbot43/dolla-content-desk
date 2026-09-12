"""Backward-compatible launcher for the Dolla Content Desk Flask app.

All routes live in app.py so importing or running the app directly has the complete workflow.
This launcher also keeps the local content repo in sync with GitHub while the desk is open.

Queue sync is semantic rather than line-based: scheduled GitHub publishing can remove live articles
while the desktop may still have additional approved articles that have not reached GitHub yet.
When the only local change is content/queue.json, the launcher merges local + remote by slug,
removes anything already published remotely, updates the local dashboard state, and pushes any
local-only queued articles safely. Other dirty local files are left completely alone.
"""
from __future__ import annotations

import json
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


def _json_file(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _remote_json(repo: Path, path: str, default):
    result = _git(repo, "show", f"origin/main:{path}")
    if result.returncode != 0:
        return default
    try:
        return json.loads(result.stdout)
    except Exception:
        return default


def _merge_queue(local_queue: list[dict], remote_queue: list[dict], remote_published: dict) -> list[dict]:
    published_slugs = set(remote_published.keys())
    local_by_slug = {
        str(item.get("slug", "")): item
        for item in local_queue
        if isinstance(item, dict) and item.get("slug") and item.get("slug") not in published_slugs
    }

    merged: list[dict] = []
    seen: set[str] = set()

    # Keep GitHub's FIFO order, using the local reviewed copy when the same slug exists on both.
    for item in remote_queue:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug", ""))
        if not slug or slug in published_slugs or slug in seen:
            continue
        merged.append(local_by_slug.get(slug, item))
        seen.add(slug)

    # Then preserve articles that only exist on this PC, in their local order.
    for item in local_queue:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug", ""))
        if not slug or slug in published_slugs or slug in seen:
            continue
        merged.append(item)
        seen.add(slug)

    return merged


def _dirty_paths(repo: Path) -> list[str]:
    status = _git(repo, "status", "--porcelain")
    if status.returncode != 0:
        return ["__git_error__"]
    paths: list[str] = []
    for line in status.stdout.splitlines():
        raw = line[3:] if len(line) >= 4 else ""
        rel = raw.split(" -> ")[-1].strip()
        if rel:
            paths.append(rel)
    return paths


def _sync_content_repo_once(repo: Path) -> None:
    """Synchronise scheduled publisher changes without losing this PC's queued articles."""
    if not (repo / ".git").exists():
        return

    dirty = _dirty_paths(repo)
    # If an image/article/etc. is being edited locally, do nothing. The normal queue push path has
    # its own semantic merge and will protect that work later.
    if any(path not in {"content/queue.json"} for path in dirty):
        return

    queue_path = repo / "content" / "queue.json"
    local_queue = _json_file(queue_path, [])

    fetch = _git(repo, "fetch", "origin", "main")
    if fetch.returncode != 0:
        return

    remote_queue = _remote_json(repo, "content/queue.json", [])
    remote_published = _remote_json(repo, "content/published.json", {})

    # A completely clean repo can just fast-forward. This is the common nightly-publisher case.
    if not dirty:
        pull = _git(repo, "pull", "--ff-only", "origin", "main")
        if pull.returncode == 0:
            return
        # If local history diverged despite a clean worktree, fall through to semantic recovery.

    merged = _merge_queue(local_queue, remote_queue, remote_published)

    # Only queue.json is dirty, so reset is safe here. It updates published.json/static pages to the
    # scheduled publisher's latest commit, then restores the merged unpublished queue.
    reset = _git(repo, "reset", "--hard", "origin/main")
    if reset.returncode != 0:
        return

    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    # If this PC had queued articles GitHub did not know about, persist the merged queue remotely.
    if merged != remote_queue:
        add = _git(repo, "add", "--", "content/queue.json")
        if add.returncode != 0:
            return
        diff = _git(repo, "diff", "--cached", "--quiet")
        if diff.returncode == 1:
            commit = _git(repo, "commit", "-m", "Sync local queue with scheduled publisher")
            if commit.returncode != 0:
                return
            push = _git(repo, "push", "origin", "main")
            if push.returncode != 0:
                # Keep the commit/local queue intact. The next normal queue operation can retry its
                # semantic merge; never force-push here.
                return


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
