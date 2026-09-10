"""Make Content Desk Git pushes resilient when GitHub advanced since the last local sync.

The desk often runs for a long review session while GitHub Actions or another maintenance commit
moves origin/main forward. A plain `git push` then fails with fetch-first. This installer replaces
app.commit_and_push with a safe version that commits the reviewed local change, fetches origin/main,
rebases the local commit on top, and only then pushes. It never force-pushes.
"""
from __future__ import annotations


def install(desk) -> None:
    def commit_and_push(paths: set[str], message: str) -> bool:
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

        fetch = desk.run_git("fetch", "origin", "main")
        if fetch.returncode != 0:
            raise RuntimeError(fetch.stderr.strip() or fetch.stdout.strip() or "git fetch failed")

        rebase = desk.run_git("rebase", "origin/main")
        if rebase.returncode != 0:
            # Never leave the user's content repo stuck in an in-progress rebase.
            desk.run_git("rebase", "--abort")
            raise RuntimeError(
                "GitHub changed the same content while this article was being queued, so the automatic "
                "rebase was stopped safely. No force-push was attempted. "
                + (rebase.stderr.strip() or rebase.stdout.strip() or "git rebase failed")
            )

        push = desk.run_git("push", "origin", "main")
        if push.returncode != 0:
            raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push failed")
        return committed

    desk.commit_and_push = commit_and_push
