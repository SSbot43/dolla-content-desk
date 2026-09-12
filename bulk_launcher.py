"""Backward-compatible launcher for the Dolla Content Desk Flask app.

All routes live in app.py so importing or running the app directly has the complete workflow.
This launcher keeps the local content repo in sync with GitHub while the desk is open.

Scheduled publishing changes queue.json/published.json/static pages remotely. The local desk can also
have approved queue entries or unrelated image/article edits that have not been pushed yet. Sync is
therefore semantic: preserve local unpublished queue entries by slug, protect unrelated dirty files
in a temporary stash, fast-forward/reset to origin/main, restore the merged queue, and then restore
unrelated local work. Already-published slugs are never resurrected.
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

    for item in remote_queue:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug", ""))
        if not slug or slug in published_slugs or slug in seen:
            continue
        merged.append(local_by_slug.get(slug, item))
        seen.add(slug)

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
        return []
    paths: list[str] = []
    for line in status.stdout.splitlines():
        raw = line[3:] if len(line) >= 4 else ""
        rel = raw.split(" -> ")[-1].strip()
        if rel:
            paths.append(rel)
    return paths


def _sync_content_repo_once(repo: Path) -> None:
    """Merge local queued work with the latest scheduled-publisher state."""
    if not (repo / ".git").exists():
        print(f"[Content Desk] sync skipped: no git repo at {repo}", flush=True)
        return

    queue_path = repo / "content" / "queue.json"
    local_queue = _json_file(queue_path, [])
    dirty = _dirty_paths(repo)
    unrelated = [p for p in dirty if p != "content/queue.json"]
    stashed = False

    if unrelated:
        stash = _git(repo, "stash", "push", "-u", "-m", "dolla-dashboard-autostash", "--", *unrelated)
        if stash.returncode != 0:
            print("[Content Desk] sync skipped: could not protect local files:", stash.stderr.strip() or stash.stdout.strip(), flush=True)
            return
        stashed = "No local changes" not in (stash.stdout or "")

    try:
        fetch = _git(repo, "fetch", "origin", "main")
        if fetch.returncode != 0:
            print("[Content Desk] sync fetch failed:", fetch.stderr.strip() or fetch.stdout.strip(), flush=True)
            return

        remote_queue = _remote_json(repo, "content/queue.json", [])
        remote_published = _remote_json(repo, "content/published.json", {})
        merged = _merge_queue(local_queue, remote_queue, remote_published)

        reset = _git(repo, "reset", "--hard", "origin/main")
        if reset.returncode != 0:
            print("[Content Desk] sync reset failed:", reset.stderr.strip() or reset.stdout.strip(), flush=True)
            return

        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

        if merged != remote_queue:
            add = _git(repo, "add", "--", "content/queue.json")
            if add.returncode == 0:
                diff = _git(repo, "diff", "--cached", "--quiet")
                if diff.returncode == 1:
                    commit = _git(repo, "commit", "-m", "Sync local queue with scheduled publisher")
                    if commit.returncode == 0:
                        push = _git(repo, "push", "origin", "main")
                        if push.returncode != 0:
                            print("[Content Desk] queue sync push failed; local merge preserved:", push.stderr.strip() or push.stdout.strip(), flush=True)
                        else:
                            print(f"[Content Desk] sync complete: {len(merged)} queued, {len(remote_published)} live", flush=True)
                    else:
                        print("[Content Desk] sync commit failed:", commit.stderr.strip() or commit.stdout.strip(), flush=True)
                else:
                    print(f"[Content Desk] sync complete: {len(merged)} queued, {len(remote_published)} live", flush=True)
        else:
            print(f"[Content Desk] sync complete: {len(merged)} queued, {len(remote_published)} live", flush=True)
    finally:
        if stashed:
            pop = _git(repo, "stash", "pop", "--index")
            if pop.returncode != 0:
                print("[Content Desk] WARNING: local files remain safe in git stash:", pop.stderr.strip() or pop.stdout.strip(), flush=True)


def _sync_loop(repo: Path) -> None:
    while True:
        time.sleep(max(15, SYNC_SECONDS))
        try:
            _sync_content_repo_once(repo)
        except Exception as exc:
            print(f"[Content Desk] sync error: {exc}", flush=True)


if __name__ == "__main__":
    content_repo = Path(os.environ.get("CONTENT_REPO", str(desk.CONTENT_REPO))).resolve()
    print(f"[Content Desk] content repo: {content_repo}", flush=True)

    # Do the first reconciliation synchronously, before Flask starts. This guarantees the dashboard
    # cannot render stale counters from yesterday's local queue/published files.
    try:
        _sync_content_repo_once(content_repo)
    except Exception as exc:
        print(f"[Content Desk] startup sync error: {exc}", flush=True)

    threading.Thread(target=_sync_loop, args=(content_repo,), daemon=True).start()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True, use_reloader=False)
