"""Queue policy + manual breaking-news publish support for Dolla Content Desk.

Normal approved articles are auto-slotted by the ramp. A manual immediate publish is an explicit
editorial override: it still must pass the quality gate, but it does not consume or wait for the
normal daily ramp cap.
"""
from __future__ import annotations

from datetime import date


def install(desk) -> None:
    """Install auto-slot queue behavior and the /publish-now route onto the existing Flask app."""

    def auto_queue_brief(brief):
        # Dates are an engine concern, not an editor concern. Recalculate the next free ramp slot
        # every time an article is approved, ignoring any stale/manual date that arrived from a form.
        queue = [b for b in desk.load_queue() if b.slug != brief.slug]
        brief.publish_date = desk.next_slot(queue)
        brief.status = "queued"
        desk.save_queue(queue + [brief])
        return brief

    # Existing /queue-local route resolves this module global at request time, so replacing it here
    # upgrades the policy without duplicating the route or forking app.py.
    desk.queue_brief = auto_queue_brief

    @desk.app.route("/publish-now", methods=["POST"])
    def publish_now():
        import json
        from flask import request
        from dolla_content import publish as pub

        brief = desk.Brief.from_dict(json.loads(request.form["brief_json"]))
        result = desk.gate_run(brief, published_bodies=desk.comparison_bodies(brief.slug))
        if not result.ok:
            return desk.show_review(
                brief,
                error="Still blocked — fix the blocking issues before publishing.",
            )
        brief = result.fixed_brief or brief

        published = pub._load_published()
        if brief.slug in published:
            return desk.show_review(
                brief,
                error="This article is already published. Nothing was changed.",
            )

        today = date.today()
        brief.publish_date = today.isoformat()
        brief.status = "live"

        # Render exactly one approved article, deliberately outside the ramp cap.
        pub.GUIDES_DIR.mkdir(parents=True, exist_ok=True)
        pub._ensure_index()
        pub._ensure_sitemap()
        cards = pub._existing_block(pub.INDEX, pub.CARD_START, pub.CARD_END)
        urls = pub._existing_block(pub.SITEMAP, pub.URL_START, pub.URL_END)
        art = pub.render(brief)
        (pub.GUIDES_DIR / f"{brief.slug}.html").write_text(art.html, encoding="utf-8")
        cards += (
            f'\n<li class="card"><a href="/guides/{brief.slug}">'
            f'<h3>{brief.title}</h3><p>{brief.meta_description}</p></a></li>'
        )
        urls += (
            f'\n  <url><loc>{pub.SITE}/guides/{brief.slug}</loc>'
            f'<lastmod>{today.isoformat()}</lastmod></url>'
        )
        published[brief.slug] = {
            "slug": brief.slug,
            "title": brief.title,
            "description": brief.meta_description,
            "scheduled_date": today.isoformat(),
            "published_date": today.isoformat(),
            "status": "live",
            "publish_mode": "manual-immediate",
            "body": brief.body_md,
        }
        pub._insert_between(pub.INDEX, pub.CARD_START, pub.CARD_END, cards)
        pub._insert_between(pub.SITEMAP, pub.URL_START, pub.URL_END, urls)
        pub._save_published(published)
        pub._save_queue([b for b in pub._load_queue() if b.slug != brief.slug])

        paths = {
            "content/queue.json",
            "content/published.json",
            "static/index.html",
            "static/sitemap.xml",
            f"static/guides/{brief.slug}.html",
        }
        image_path = desk.image_repo_path(brief.image)
        if image_path:
            paths.add(image_path)

        try:
            desk.commit_and_push(paths, f"Publish breaking Dolla guide {brief.slug}")
        except Exception as exc:
            return desk.show_review(
                brief,
                error=(
                    "Article was rendered locally, but GitHub push failed: " + str(exc)
                ),
            )

        return desk.show_review(
            brief,
            notice=(
                "Published immediately outside the normal ramp queue. "
                f"Cloudflare should deploy /guides/{brief.slug} shortly."
            ),
        )
