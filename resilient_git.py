"""Resilient Git publishing for Content Desk.

`content/queue.json` is a shared generated file. GitHub Actions and the desktop desk can both
change it, so line-based rebases are the wrong tool: two perfectly valid queue edits conflict even
when they concern different articles.

This installer replaces app.commit_and_push with a queue-aware synchroniser. Before each push it:
1. snapshots the queue/change being approved,
2. temporarily stashes unrelated local work (such as other article images),
3. fetches origin/main,
4. rebuilds the local queue on top of the remote queue by article slug,
5. never resurrects a slug that is already published remotely,
6. restores any files owned by this operation,
7. commits and pushes from the fresh remote head,
8. restores the unrelated local work.

If origin moves again during the push, it retries the merge once. It never force-pushes.
"""
from __future__ import annotations

import json
from pathlib import Path


def install(desk) -> None:
    repo = Path(desk.CONTENT_REPO)

    def _read_json_file(path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _remote_json(path: str, default):
        result = desk.run_git("show", f"origin/main:{path}")
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

        # Preserve GitHub FIFO order; replace same-slug entries with this PC's reviewed copy.
        for item in remote_queue:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", ""))
            if not slug or slug in published_slugs or slug in seen:
                continue
            merged.append(local_by_slug.get(slug, item))
            seen.add(slug)

        # Append articles that exist only on this PC in local queue order.
        for item in local_queue:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", ""))
            if not slug or slug in published_slugs or slug in seen:
                continue
            merged.append(item)
            seen.add(slug)

        return merged

    def _snapshot_files(paths: set[str]) -> dict[str, bytes]:
        snapshots: dict[str, bytes] = {}
        for rel in paths:
            if rel == "content/queue.json":
                continue
            path = repo / rel
            if path.exists() and path.is_file():
                snapshots[rel] = path.read_bytes()
        return snapshots

    def _restore_files(snapshots: dict[str, bytes]) -> None:
        for rel, data in snapshots.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def _dirty_paths_excluding(owned_paths: set[str]) -> list[str]:
        status = desk.run_git("status", "--porcelain")
        if status.returncode != 0:
            raise RuntimeError(status.stderr.strip() or "git status failed")
        dirty: list[str] = []
        for line in status.stdout.splitlines():
            raw = line[3:] if len(line) >= 4 else ""
            # For renames porcelain may say "old -> new". Keep the destination path.
            rel = raw.split(" -> ")[-1].strip()
            if rel and rel not in owned_paths:
                dirty.append(rel)
        return dirty

    def _stash_unrelated(paths: list[str]) -> bool:
        if not paths:
            return False
        # Stash only unrelated paths. The queue and the article currently being approved stay
        # available through our snapshots and are rebuilt after syncing origin/main.
        result = desk.run_git("stash", "push", "-u", "-m", "dolla-content-desk-autostash", "--", *paths)
        if result.returncode != 0:
            raise RuntimeError(
                "Could not temporarily protect unrelated local files before queue sync: "
                + (result.stderr.strip() or result.stdout.strip() or "git stash failed")
            )
        return "No local changes" not in (result.stdout or "")

    def _restore_unrelated(stashed: bool) -> None:
        if not stashed:
            return
        result = desk.run_git("stash", "pop", "--index")
        if result.returncode != 0:
            # The reviewed article may already be safely pushed. Do not lose the stash; surface a
            # precise warning so the user can recover it, rather than silently discarding work.
            raise RuntimeError(
                "Article push completed, but unrelated local work could not be restored automatically. "
                "It is still safe in git stash. "
                + (result.stderr.strip() or result.stdout.strip() or "git stash pop failed")
            )

    def _rebase_queue_semantically(paths: set[str]) -> None:
        queue_path = repo / "content" / "queue.json"
        local_queue = _read_json_file(queue_path, [])
        file_snapshots = _snapshot_files(paths)

        fetch = desk.run_git("fetch", "origin", "main")
        if fetch.returncode != 0:
            raise RuntimeError(fetch.stderr.strip() or fetch.stdout.strip() or "git fetch failed")

        remote_queue = _remote_json("content/queue.json", [])
        remote_published = _remote_json("content/published.json", {})
        merged_queue = _merge_queue(local_queue, remote_queue, remote_published)

        # Owned changes are snapshotted; unrelated work has already been stashed. A hard reset is
        # now safe and clears stale local queue commits that would otherwise keep conflicting.
        reset = desk.run_git("reset", "--hard", "origin/main")
        if reset.returncode != 0:
            raise RuntimeError(reset.stderr.strip() or reset.stdout.strip() or "git reset to origin/main failed")

        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(json.dumps(merged_queue, indent=2, ensure_ascii=False), encoding="utf-8")
        _restore_files(file_snapshots)

    def commit_and_push(paths: set[str], message: str) -> bool:
        paths = set(paths)
        unrelated = _dirty_paths_excluding(paths)
        stashed = _stash_unrelated(unrelated)
        pushed = False
        committed_any = False
        try:
            for attempt in range(2):
                _rebase_queue_semantically(paths)

                add = desk.run_git("add", "--", *sorted(paths))
                if add.returncode != 0:
                    raise RuntimeError(add.stderr.strip() or "git add failed")

                diff = desk.run_git("diff", "--cached", "--quiet")
                committed = False
                if diff.returncode == 1:
                    commit = desk.run_git("commit", "-m", message)
                    if commit.returncode != 0:
                        raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")
                    committed = True
                    committed_any = True
                elif diff.returncode != 0:
                    raise RuntimeError(diff.stderr.strip() or "git diff failed")

                push = desk.run_git("push", "origin", "main")
                if push.returncode == 0:
                    pushed = True
                    break

                text = (push.stderr or push.stdout or "").lower()
                if attempt == 0 and ("fetch first" in text or "non-fast-forward" in text or "rejected" in text):
                    continue
                raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push failed")

            if not pushed:
                raise RuntimeError("GitHub changed twice during this queue operation; please retry the article once.")
        finally:
            # Always try to put unrelated images/edits back exactly where the user left them.
            _restore_unrelated(stashed)

        return committed_any

    desk.commit_and_push = commit_and_push
