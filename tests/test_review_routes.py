import ast
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
import immediate_publish
import manual_override

ROOT = Path(__file__).resolve().parents[1]


class Brief:
    def __init__(self, **values):
        self.__dict__.update(values)
        self.gate_override = values.get("gate_override", False)

    @classmethod
    def from_dict(cls, values):
        return cls(**values)


class ReviewRoutesTests(unittest.TestCase):
    def setUp(self):
        self.desk = types.ModuleType("test_desk_bootstrap")
        self.desk.app = Flask(__name__)
        self.desk.Brief = Brief
        self.desk.load_queue = Mock(return_value=[])
        self.desk.save_queue = Mock()
        self.desk.next_slot = Mock(return_value="2026-09-18")
        self.desk.push_queue = Mock()
        self.desk.comparison_bodies = Mock(return_value=[])
        self.desk.gate_run = Mock(return_value=types.SimpleNamespace(ok=False, fixed_brief=None))
        self.desk.show_review = lambda brief, **kw: {
            "slug": brief.slug, "override": brief.gate_override,
            "status": getattr(brief, "status", "proposed"), **kw
        }
        # Execute the real app's top-level registration calls. Their placement is
        # what makes direct Flask/app.py startup work without bulk_launcher.
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        calls = [n for n in tree.body if isinstance(n, ast.Expr)
                 and isinstance(n.value, ast.Call)
                 and isinstance(n.value.func, ast.Name)
                 and n.value.func.id in {"install_publish_policy", "install_manual_override"}]
        self.assertEqual(len(calls), 2)
        with patch.dict(sys.modules, {self.desk.__name__: self.desk}):
            exec(compile(ast.Module(body=calls, type_ignores=[]), "app.py", "exec"), {
                "__name__": self.desk.__name__, "sys": sys,
                "install_publish_policy": immediate_publish.install,
                "install_manual_override": manual_override.install,
            })
        self.client = self.desk.app.test_client()
        self.form = {"brief_json": json.dumps({"slug": "red-post", "body_md": "reviewed body"})}

    def test_override_queues_and_starts_background_sync(self):
        with patch.object(manual_override.threading, "Thread") as thread:
            response = self.client.post("/queue-override", data=self.form)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["override"])
        self.assertEqual(response.json["status"], "queued")
        saved = self.desk.save_queue.call_args.args[0][0]
        self.assertTrue(saved.gate_override)
        self.assertEqual(saved.body_md, "reviewed body")
        thread.return_value.start.assert_called_once()
        thread.call_args.kwargs["target"](*thread.call_args.kwargs["args"])
        self.desk.push_queue.assert_called_once_with(saved)

    def test_normal_approval_does_not_bypass_red_gate(self):
        with patch.object(manual_override.threading, "Thread") as thread:
            response = self.client.post("/queue-reviewed", data=self.form)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Still blocked", response.json["error"])
        self.desk.save_queue.assert_not_called()
        thread.assert_not_called()

    def test_pass_approval_queues_without_manual_override(self):
        self.desk.gate_run.return_value.ok = True
        with patch.object(manual_override.threading, "Thread"):
            response = self.client.post("/queue-reviewed", data=self.form)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["override"])
        self.desk.save_queue.assert_called_once()

    def test_installers_do_not_duplicate_routes(self):
        immediate_publish.install(self.desk)
        manual_override.install(self.desk)
        for path in ("/queue-reviewed", "/queue-override", "/publish-now"):
            rules = [r for r in self.desk.app.url_map.iter_rules() if r.rule == path]
            self.assertEqual(len(rules), 1)
            self.assertIn("POST", rules[0].methods)


if __name__ == "__main__":
    unittest.main()
