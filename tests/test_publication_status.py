import ast
import json
import subprocess
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import publication_status as status


def result(data=None, code=0):
    return SimpleNamespace(returncode=code, stdout=json.dumps(data) if data is not None else '')


class PublicationStatusTests(unittest.TestCase):
    def setUp(self):
        status._CACHE.clear()
        self.local = {f'guide-{i}': {'slug': f'guide-{i}'} for i in range(30)}
        self.remote = {f'guide-{i}': {'slug': f'guide-{i}'} for i in range(50)}
        self.repo = Path('.')

    def test_stale_local_30_uses_remote_50_without_changing_local(self):
        with patch.object(status, '_git', side_effect=[result(), result(self.remote)]) as git:
            records, note = status.dashboard_publications(self.repo, self.local)
        self.assertEqual(len(records), 50)
        self.assertEqual(len(self.local), 30)
        self.assertIn('Checked', note)
        self.assertEqual([call.args[1] for call in git.call_args_list], ['fetch', 'show'])

    def test_offline_remote_snapshot_is_labelled(self):
        with patch.object(status, '_git', side_effect=[subprocess.TimeoutExpired('git', 8), result(self.remote)]):
            records, note = status.dashboard_publications(self.repo, self.local)
        self.assertEqual(len(records), 50)
        self.assertIn('Offline', note)

    def test_no_remote_uses_local_with_warning(self):
        with patch.object(status, '_git', return_value=result(code=1)):
            records, note = status.dashboard_publications(self.repo, self.local)
        self.assertEqual(records, self.local)
        self.assertIn('out of date', note)

    def test_empty_remote_is_authoritative_not_replaced_by_local(self):
        with patch.object(status, '_git', side_effect=[result(), result({})]):
            records, _ = status.dashboard_publications(self.repo, self.local)
        self.assertEqual(records, {})

    def test_bad_remote_data_is_not_shown(self):
        with patch.object(status, '_git', side_effect=[result(), result(['bad'])]):
            records, note = status.dashboard_publications(self.repo, self.local)
        self.assertEqual(records, self.local)
        self.assertIn('out of date', note)

    def test_cache_expires_and_fetches_new_count(self):
        with patch.object(status, '_git', side_effect=[result(), result(self.remote), result(), result({**self.remote, 'new': {}})]) as git, patch.object(status.time, 'monotonic', side_effect=[0, 10, 60, 60]):
            self.assertEqual(len(status.dashboard_publications(self.repo, self.local)[0]), 50)
            self.assertEqual(len(status.dashboard_publications(self.repo, self.local)[0]), 50)
            self.assertEqual(len(status.dashboard_publications(self.repo, self.local)[0]), 51)
            self.assertEqual(git.call_count, 4)

    def test_dashboard_counts_all_remote_guides_and_excludes_them_from_queue(self):
        # Execute the real route with dependencies injected, without starting Flask or AI clients.
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        if not app_path.exists():
            app_path = Path(__file__).with_name('app.py')
        tree = ast.parse(app_path.read_text(encoding='utf-8-sig'))
        route = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'dashboard')
        route.decorator_list = []
        queue = [SimpleNamespace(slug=f'guide-{i}', body_md='body', publish_date='') for i in range(55)]
        import os
        namespace = dict(load_queue=lambda: queue, load_published=lambda: self.local,
                         dashboard_publications=lambda *args: (self.remote, 'Checked'),
                         CONTENT_REPO=self.repo, daily_cap=lambda d: 10, date=date,
                         render_template=lambda template, **context: context, os=os, SITE_BASE='https://example.com')
        exec(compile(ast.Module(body=[route], type_ignores=[]), str(app_path), 'exec'), namespace)
        context = namespace['dashboard']()
        self.assertEqual(context['live'], 50)
        self.assertEqual(context['queued'], 5)
        self.assertEqual(len(context['published']), 25)
        self.assertEqual(context['publication_note'], 'Checked')


if __name__ == '__main__':
    unittest.main()

