import unittest
import json
from pathlib import Path
from unittest.mock import patch

import app as desk


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
        desk.app.config.update(TESTING=True)
        self.client = desk.app.test_client()

    def approved_brief(self, slug="approved", image=""):
        return desk.Brief(
            slug=slug,
            title="A practical Dolla casino guide",
            meta_description=(
                "A practical Dolla casino guide covering controls, crypto deposit choices, "
                "session limits, and useful checks before play begins."
            ),
            h1="A practical Dolla casino guide",
            body_md=article_body(),
            primary_keyword="practical dolla casino guide",
            image=image,
        )

    def assert_image_less_review_can_continue(self, response):
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("PASS — ready to queue or publish", page)
        self.assertIn("no-image", page)
        self.assertNotRegex(page, r"<button[^>]*disabled[^>]*>Approve & queue")
        self.assertNotRegex(page, r"<button[^>]*disabled[^>]*>Publish immediately")

    def test_single_article_flow_allows_no_image(self):
        response = self.client.post("/feed", data=form_data("paste"))
        self.assert_image_less_review_can_continue(response)

    def test_app_dashboard_renders_with_bulk_push_endpoint(self):
        waiting = self.approved_brief()
        with (
            patch.object(desk, "load_queue", return_value=[waiting]),
            patch.object(desk, "load_published", return_value={}),
        ):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('action="/push-queued-all"', page)
        self.assertIn("Push all queued (1)", page)

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

    def test_auto_brief_keeps_selected_destination_consistent(self):
        brief = desk.Brief(slug="void", title="The Void Run Phenomenon", game="voidrun")
        with patch.dict(desk.os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            completed = desk.complete_headline_brief(brief)

        self.assertIn("VOID Run", completed.meta_description)
        self.assertIn("VOID Run", completed.why_dolla)
        self.assertNotIn("Olympus", completed.meta_description + completed.why_dolla)

    def test_destination_guesser_separates_void_run_from_generic_crash(self):
        self.assertEqual(desk._guess_destination("The Void Run Phenomenon"), "voidrun")
        self.assertEqual(desk._guess_destination("The Ultimate Crash Cash-Out"), "crash")
        self.assertEqual(desk._guess_destination("The Big Heist Vault Breaker"), "bigscore")
        self.assertEqual(desk._guess_destination("The Blazing Inferno Streak"), "inferno")
        self.assertEqual(desk._guess_destination("The Dolla.fo Olympus Smash"), "olympus")

    def test_attached_image_without_alt_still_blocks(self):
        data = form_data("paste")
        data["image"] = "https://example.com/article.webp"

        response = self.client.post("/review", data=data)

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("BLOCKED — fix the red issues", page)
        self.assertIn("no-alt", page)
        self.assertRegex(page, r"<button[^>]*disabled[^>]*>Approve & queue")
        self.assertRegex(page, r"<button[^>]*disabled[^>]*>Publish immediately")

    def test_queue_for_later_saves_locally_without_git_push(self):
        approved = self.approved_brief()
        with (
            patch.object(desk, "comparison_bodies", return_value=[]),
            patch.object(desk, "queue_brief", return_value=approved) as queue_brief,
            patch.object(desk, "commit_and_push") as commit_and_push,
        ):
            response = self.client.post(
                "/queue-local",
                data={"brief_json": json.dumps(approved.to_dict())},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Queued locally", response.get_data(as_text=True))
        queue_brief.assert_called_once()
        commit_and_push.assert_not_called()

    def test_windows_launcher_overrides_stale_content_repo_path(self):
        launcher_source = (Path(desk.__file__).parent / "START_WINDOWS.bat").read_text(encoding="utf-8")

        self.assertIn('set "CONTENT_REPO=%ENGINE_DIR%"', launcher_source)
        self.assertLess(
            launcher_source.index('set "CONTENT_REPO=%ENGINE_DIR%"'),
            launcher_source.index('py bulk_launcher.py'),
        )

    def test_push_all_queued_commits_queue_and_all_local_images_once(self):
        already_live = desk.Brief(slug="already-live", body_md=article_body())
        waiting = desk.Brief(
            slug="waiting",
            body_md=article_body(),
            image="https://dollacasino.com/img/guides/waiting.webp",
        )
        second = desk.Brief(
            slug="second",
            body_md=article_body(),
            image="https://dollacasino.com/img/guides/second.png",
        )

        with (
            patch.object(desk, "load_queue", return_value=[already_live, waiting, second]),
            patch.object(desk, "load_published", return_value={"already-live": {}}),
            patch.object(
                desk,
                "image_repo_path",
                side_effect=lambda image: {
                    waiting.image: "static/img/guides/waiting.webp",
                    second.image: "static/img/guides/second.png",
                }.get(image),
            ),
            patch.object(desk, "commit_and_push") as commit_and_push,
        ):
            response = self.client.post("/push-queued-all")

        self.assertEqual(response.status_code, 302)
        self.assertIn("pushed=2", response.headers["Location"])
        paths, message = commit_and_push.call_args.args
        self.assertEqual(paths, {
            "content/queue.json",
            "static/img/guides/waiting.webp",
            "static/img/guides/second.png",
        })
        self.assertIn("Queue Dolla content batch", message)
        self.assertEqual(commit_and_push.call_count, 1)


if __name__ == "__main__":
    unittest.main()
