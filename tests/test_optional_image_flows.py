import unittest
from pathlib import Path
from unittest.mock import patch

import bulk_launcher as launcher

desk = launcher.desk


def article_body() -> str:
    paragraph = (
        "Dolla players can review crypto deposit choices, read the controls, and set a limit "
        "before a session. The article explains the experience in direct, practical terms. "
    )
    return "## Before you play\n\n" + paragraph * 35 + "\n\n## During a session\n\n" + paragraph * 35


def form_data(mode: str) -> dict[str, str]:
    return {
        "mode": mode,
        "title": "A practical Dolla casino guide",
        "meta": (
            "A practical Dolla casino guide covering controls, crypto deposit choices, "
            "session limits, and useful checks before play begins."
        ),
        "h1": "A practical Dolla casino guide",
        "body": article_body() if mode == "paste" else "",
        "market": "US",
        "game": "",
        "image": "",
        "alt": "",
    }


class OptionalImageFlowTests(unittest.TestCase):
    def setUp(self):
        launcher.app.config.update(TESTING=True)
        self.client = launcher.app.test_client()

    def assert_image_less_review_can_continue(self, response):
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("PASS — ready to queue or publish", page)
        self.assertIn("no-image", page)
        self.assertNotRegex(page, r"<button[^>]*disabled[^>]*>Queue for later")
        self.assertNotRegex(page, r"<button[^>]*disabled[^>]*>Publish &(?:amp;)? Push")

    def test_single_article_flow_allows_no_image(self):
        response = self.client.post("/feed", data=form_data("paste"))
        self.assert_image_less_review_can_continue(response)

    def test_batch_style_generation_allows_no_image(self):
        def fake_generate(brief, published_bodies=None):
            brief.body_md = article_body()
            return brief, desk.gate_run(brief, published_bodies=published_bodies)

        with patch.object(desk.gen, "generate", side_effect=fake_generate):
            response = self.client.post("/feed", data=form_data("generate"))

        self.assert_image_less_review_can_continue(response)

    def test_batch_page_only_demands_alt_for_selected_images(self):
        source = (Path(desk.__file__).parent / "static" / "batch.html").read_text(encoding="utf-8")

        self.assertIn("const missingAlt=raw.filter(r=>topicFiles[r]&&!(topicAlts[r]||'').trim())", source)
        self.assertIn("if(r.file)fd.append('image_file',r.file,r.file.name)", source)
        self.assertNotIn("!topicFiles[r]||!(topicAlts[r]||'').trim()", source)

    def test_attached_image_without_alt_still_blocks(self):
        data = form_data("paste")
        data["image"] = "https://example.com/article.webp"

        response = self.client.post("/review", data=data)

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("BLOCKED — fix the red issues", page)
        self.assertIn("no-alt", page)
        self.assertRegex(page, r"<button[^>]*disabled[^>]*>Queue for later")
        self.assertRegex(page, r"<button[^>]*disabled[^>]*>Publish &(?:amp;)? Push")

    def test_windows_launcher_overrides_stale_content_repo_path(self):
        launcher_source = (Path(desk.__file__).parent / "START_WINDOWS.bat").read_text(encoding="utf-8")

        self.assertIn('set "CONTENT_REPO=%ENGINE_DIR%"', launcher_source)
        self.assertLess(
            launcher_source.index('set "CONTENT_REPO=%ENGINE_DIR%"'),
            launcher_source.index('py bulk_launcher.py'),
        )

    def test_push_all_queued_ignores_already_published_history(self):
        already_live = desk.Brief(slug="already-live", body_md=article_body())
        waiting = desk.Brief(slug="waiting", body_md=article_body())

        with (
            patch.object(desk, "load_queue", return_value=[already_live, waiting]),
            patch.object(desk, "load_published", return_value={"already-live": {}}),
            patch.object(desk, "commit_and_push") as commit_and_push,
        ):
            response = self.client.post("/push-queued-all")

        self.assertEqual(response.status_code, 302)
        self.assertIn("pushed=1", response.headers["Location"])
        commit_and_push.assert_called_once()


if __name__ == "__main__":
    unittest.main()
