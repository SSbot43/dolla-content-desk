import ast
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import encoding_git
import resilient_git


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


class QueueSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote, self.local, self.worker = [root / name for name in ("remote.git", "desk", "publisher")]
        self.remote.mkdir()
        git(self.remote, "init", "--bare", "--initial-branch=main")
        git(root, "clone", str(self.remote), str(self.local))
        self.configure(self.local)
        (self.local / "content").mkdir()
        self.write(self.local, "queue.json", [{"slug": "old", "body_md": "old body"}])
        self.write(self.local, "published.json", {})
        git(self.local, "add", ".")
        git(self.local, "commit", "-m", "Initial queue")
        git(self.local, "push", "-u", "origin", "main")
        git(root, "clone", str(self.remote), str(self.worker))
        self.configure(self.worker)
        self.desk = types.ModuleType("sync_test_desk")
        self.desk.CONTENT_REPO = self.local
        # Execute app.py's actual top-level sync registration, with no Flask/AI startup.
        source = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        names = {"install_encoding_git", "install_resilient_git"}
        calls = [node for node in tree.body if isinstance(node, ast.Expr)
                 and isinstance(node.value, ast.Call)
                 and isinstance(node.value.func, ast.Name)
                 and node.value.func.id in names]
        self.assertEqual([n.value.func.id for n in calls], ["install_encoding_git", "install_resilient_git"])
        with patch.dict(sys.modules, {self.desk.__name__: self.desk}):
            exec(compile(ast.Module(body=calls, type_ignores=[]), str(source), "exec"), {
                "__name__": self.desk.__name__, "sys": sys,
                "install_encoding_git": encoding_git.install,
                "install_resilient_git": resilient_git.install,
            })

    def configure(self, repo):
        git(repo, "config", "user.name", "Regression Tests")
        git(repo, "config", "user.email", "tests@example.invalid")

    def write(self, repo, filename, data):
        (repo / "content" / filename).write_text(json.dumps(data), encoding="utf-8")

    def publish_remotely(self, slug="remote-only"):
        self.write(self.worker, "queue.json", [{"slug": slug, "body_md": "remote body"}])
        self.write(self.worker, "published.json", {"old": {"slug": "old"}})
        git(self.worker, "add", ".")
        git(self.worker, "commit", "-m", "Scheduled publisher changed queue")
        git(self.worker, "push")

    def approve_locally(self):
        self.write(self.local, "queue.json", [
            {"slug": "old"}, {"slug": "reviewed", "body_md": "Reviewed text", "gate_override": True}
        ])
        (self.local / "unrelated-image.txt").write_text("preserve my unsaved image")

    def assert_remote_and_local_safe(self, remote_slug):
        queue = json.loads(git(self.remote, "show", "main:content/queue.json"))
        self.assertEqual([row["slug"] for row in queue], [remote_slug, "reviewed"])
        self.assertTrue(queue[1]["gate_override"])
        self.assertEqual((self.local / "unrelated-image.txt").read_text(), "preserve my unsaved image")
        self.assertEqual(git(self.local, "stash", "list"), "")

    def test_behind_remote_merges_reviewed_override_without_losing_work(self):
        self.publish_remotely()
        self.approve_locally()
        self.desk.commit_and_push({"content/queue.json"}, "Queue reviewed article")
        self.assert_remote_and_local_safe("remote-only")

    def test_publisher_moving_during_push_is_retried_without_force_push(self):
        self.approve_locally()
        run = self.desk.run_git
        pushes = []

        def move_before_push(*args):
            if args[0] == "push":
                pushes.append(args)
                if len(pushes) == 1:
                    self.publish_remotely("racing-publisher")
            return run(*args)

        self.desk.run_git = move_before_push
        self.desk.commit_and_push({"content/queue.json"}, "Queue reviewed article")
        self.assertEqual(len(pushes), 2)
        self.assertFalse(any("--force" in args or "-f" in args for args in pushes))
        self.assert_remote_and_local_safe("racing-publisher")


if __name__ == "__main__":
    unittest.main()
