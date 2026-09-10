"""Resilient Git publishing for Content Desk.

`content/queue.json` is a shared generated file. GitHub Actions and the desktop desk can both
change it, so line-based rebases are the wrong tool: two perfectly valid queue edits conflict even
when they concern different articles.

This installer replaces app.commit_and_push with a queue-aware synchroniser. Before each push it:
1. snapshots the local queue/change being approved,
2. fetches origin/main,
3. rebuilds the local queue on top of the remote queue by article slug,
4. never resurrects a slug that is already published remotely,
5. restores any staged image files,
6. commits and pushes from the fresh remote head.

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

    def _git_text(*args: str) -> str:
        result = desk.run_git(*args)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")
        return result.stdout

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

        # Preserve GitHub's FIFO ordering. If this PC has a newer copy of the same queued article,
        # use that article body/metadata in the same position.
        for item in remote_queue:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", ""))
            if not slug or slug in published_slugs or slug in seen:
                continue
            merged.append(local_by_slug.get(slug, item))
            seen.add(slug)

        # Append articles that exist only on this PC in the order they were locally queued.
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

        # We have snapshotted every file this operation owns. Resetting to origin/main removes old
        # local queue commits that would otherwise cause the same JSON conflict on every retry.
        reset = desk.run_git("reset", "--hard", "origin/main")
        if reset.returncode != 0:
            raise RuntimeError(reset.stderr.strip() or reset.stdout.strip() or "git reset to origin/main failed")

        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(json.dumps(merged_queue, indent=2, ensure_ascii=False), encoding="utf-8")
        _restore_files(file_snapshots)

    def commit_and_push(paths: set[str], message: str) -> bool:
        paths = set(paths)

        # Do not discard unrelated uncommitted work if somebody manually edited the content repo.
        status = desk.run_git("status", "--porcelain")
        if status.returncode != 0:
            raise RuntimeError(status.stderr.strip() or "git status failed")
        dirty = []
        for line in status.stdout.splitlines():
            rel = line[3:].strip() if len(line) >= 4 else ""
            if rel and rel not in paths:
                dirty.append(rel)
        if dirty:
            raise RuntimeError(
                "Content repo has unrelated local changes, so automatic queue sync stopped safely: "
                + ", ".join(dirty[:6])
            )

        # Queue pushes use a semantic merge instead of git rebase. For other pushes this is still
        # safe because queue.json is part of every normal publishing operation in this app.
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
            elif diff.returncode != 0:
                raise RuntimeError(diff.stderr.strip() or "git diff failed")

            push = desk.run_git("push", "origin", "main")
            if push.returncode == 0:
                return committed

            text = (push.stderr or push.stdout or "").lower()
            if attempt == 0 and ("fetch first" in text or "non-fast-forward" in text or "rejected" in text):
                # Origin changed in the tiny fetch->push window. Merge again from the new remote.
                continue
            raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push failed")

        raise RuntimeError("GitHub changed twice during this queue operation; please retry the article once.")

    desk.commit_and_push = commit_and_push
